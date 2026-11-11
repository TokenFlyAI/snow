"""Open-Meteo Forecast API client.

One request per model, many coordinates per request. `elevation=nan` turns
off Open-Meteo's own downscaling so we get raw grid-cell values plus the
grid-cell elevation and do the elevation correction ourselves.

Docs: https://open-meteo.com/en/docs  (free tier: non-commercial, CC BY 4.0,
600/min, 5000/h, 10000/day; >10 variables or >14 days count as extra calls).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

import httpx
import numpy as np

from ..config import FORECAST_DAYS, PAST_DAYS, PRESSURE_LEVELS, ModelSpec
from ..resorts import Resort

log = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "snow-forecast-pipeline/0.1 (+https://github.com/TokenFlyAI/snow)"
BATCH_SIZE = 50

SURFACE_VARS = (
    "temperature_2m", "relative_humidity_2m", "precipitation", "snowfall",
    "wind_speed_10m", "wind_gusts_10m", "cloud_cover", "visibility",
    "freezing_level_height",
)
LEVEL_VARS = ("temperature", "geopotential_height", "relative_humidity", "wind_speed")


def hourly_vars() -> list[str]:
    out = list(SURFACE_VARS)
    for v in LEVEL_VARS:
        out += [f"{v}_{p}hPa" for p in PRESSURE_LEVELS]
    return out


@dataclass
class ModelData:
    """Raw hourly series of one model at one resort. Missing values are NaN."""
    model: str
    resort_id: str
    grid_elevation: float
    time: np.ndarray                  # datetime64[h], UTC
    v: dict[str, np.ndarray] = field(default_factory=dict)

    def get(self, name: str) -> np.ndarray:
        a = self.v.get(name)
        return a if a is not None else np.full(self.time.shape, np.nan)

    def level_stack(self, var: str) -> np.ndarray:
        """(n_levels, n_time) array for a pressure-level variable, lowest level first."""
        return np.stack([self.get(f"{var}_{p}hPa") for p in PRESSURE_LEVELS])

    @property
    def has_data(self) -> bool:
        return bool(np.isfinite(self.get("precipitation")).any())


class OpenMeteoError(RuntimeError):
    pass


def call_weight(n_vars: int, n_days: int, n_locations: int) -> float:
    """Approximate free-tier call accounting for one request."""
    return max(1.0, n_vars / 10.0) * max(1.0, n_days / 14.0) * n_locations


def _to_array(values: Optional[list]) -> np.ndarray:
    return np.array([np.nan if x is None else x for x in (values or [])], dtype=float)


def parse_location(payload: dict, model: str, resort_id: str) -> ModelData:
    hourly = payload["hourly"]
    t = np.array(hourly["time"], dtype="datetime64[h]")
    md = ModelData(model=model, resort_id=resort_id,
                   grid_elevation=float(payload.get("elevation") or np.nan), time=t)
    for k, vals in hourly.items():
        if k != "time":
            md.v[k] = _to_array(vals)
    return md


def _request(client: httpx.Client, params: dict, retries: int = 4) -> list[dict]:
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.get(BASE_URL, params=params, timeout=90.0)
            if r.status_code == 400:
                reason = r.json().get("reason", r.text[:200])
                raise OpenMeteoError(reason)  # not retryable
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except OpenMeteoError:
            raise
        except (httpx.HTTPError, ValueError) as e:
            last = e
            log.warning("open-meteo attempt %d/%d failed: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2.5
    raise OpenMeteoError(f"request failed after {retries} attempts: {last}")


def fetch_model(client: httpx.Client, spec: ModelSpec, resorts: Iterable[Resort],
                forecast_days: int = FORECAST_DAYS, past_days: int = PAST_DAYS,
                usage: Optional[dict] = None) -> dict[str, ModelData]:
    """Fetch one model for many resorts. Returns {resort_id: ModelData}.

    Raises OpenMeteoError if the model is unavailable; the caller drops it.
    """
    resorts = list(resorts)
    variables = hourly_vars()
    out: dict[str, ModelData] = {}
    for i in range(0, len(resorts), BATCH_SIZE):
        batch = resorts[i:i + BATCH_SIZE]
        params = {
            "latitude": ",".join(f"{r.lat:.4f}" for r in batch),
            "longitude": ",".join(f"{r.lon:.4f}" for r in batch),
            "elevation": ",".join("nan" for _ in batch),
            "models": spec.id,
            "hourly": ",".join(variables),
            "forecast_days": forecast_days,
            "past_days": past_days,
            "timezone": "GMT",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "temperature_unit": "celsius",
        }
        payloads = _request(client, params)
        if len(payloads) != len(batch):
            raise OpenMeteoError(f"{spec.id}: expected {len(batch)} locations, got {len(payloads)}")
        for r, p in zip(batch, payloads):
            out[r.id] = parse_location(p, spec.id, r.id)
        if usage is not None:
            usage["requests"] = usage.get("requests", 0) + 1
            usage["weighted_calls"] = usage.get("weighted_calls", 0.0) + call_weight(
                len(variables), forecast_days + past_days, len(batch))
    return out


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT})
