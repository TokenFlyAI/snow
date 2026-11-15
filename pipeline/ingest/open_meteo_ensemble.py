"""Open-Meteo Ensemble API client (https://ensemble-api.open-meteo.com/v1/ensemble).

One request per ensemble model and batch of resorts. We ask for a single
variable, hourly `snowfall`, at each resort's mid-mountain elevation:
Open-Meteo then downscales every member's temperature to that elevation
before splitting rain from snow, so each member carries its own rain/snow
decision. The amount uses a fixed 7:1 ratio (0.7 cm per mm of water); the
processing step rescales it with the snow-to-liquid ratio of our own blend.

Cost: every member counts as a variable, so one location costs
members / 10 x days / 14 weighted calls (GEFS, 31 members, 35 days: 7.75).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx
import numpy as np

from ..config import EnsembleSpec, call_weight
from ..resorts import Resort
from .open_meteo import OpenMeteoError, _request, _to_array, record

log = logging.getLogger(__name__)

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
VARIABLE = "snowfall"
OM_SNOW_RATIO = 7.0          # Open-Meteo: cm of snow per cm of water
BATCH_SIZE = 25              # 25 x 7.75 weighted calls stays well under the per-minute limit
_MEMBER = re.compile(rf"^{VARIABLE}(?:_member(\d+))?$")


@dataclass
class EnsembleData:
    """Hourly snowfall of every member of one ensemble at one resort (cm, 7:1 ratio, mid elevation)."""
    model: str
    resort_id: str
    time: np.ndarray        # datetime64[h], UTC, end of each hour
    members: np.ndarray     # (n_members, n_time), NaN where a member has no value

    @property
    def has_data(self) -> bool:
        return bool(self.members.size and np.isfinite(self.members).any())


def parse_members(payload: dict, model: str, resort_id: str) -> EnsembleData:
    hourly = payload["hourly"]
    t = np.array(hourly["time"], dtype="datetime64[h]")
    rows: list[tuple[int, np.ndarray]] = []
    for k, vals in hourly.items():
        m = _MEMBER.match(k)
        if m:
            rows.append((int(m.group(1) or 0), _to_array(vals)))   # the control run is member 0
    rows.sort(key=lambda x: x[0])
    members = np.stack([a for _, a in rows]) if rows else np.empty((0, t.shape[0]))
    return EnsembleData(model=model, resort_id=resort_id, time=t, members=members)


def fetch_ensemble(client: httpx.Client, spec: EnsembleSpec, resorts: Iterable[Resort],
                   usage: Optional[dict] = None) -> dict[str, EnsembleData]:
    """Fetch one ensemble model for many resorts. Returns {resort_id: EnsembleData}.

    Raises OpenMeteoError when the model is unavailable; the caller carries on without it.
    """
    resorts = list(resorts)
    out: dict[str, EnsembleData] = {}
    for i in range(0, len(resorts), BATCH_SIZE):
        batch = resorts[i:i + BATCH_SIZE]
        params = {
            "latitude": ",".join(f"{r.lat:.4f}" for r in batch),
            "longitude": ",".join(f"{r.lon:.4f}" for r in batch),
            "elevation": ",".join(str(r.elevation_m.mid) for r in batch),
            "models": spec.id,
            "hourly": VARIABLE,
            "forecast_days": spec.days,
            "timezone": "GMT",
            "precipitation_unit": "mm",
        }
        weight = call_weight(spec.members, spec.days, len(batch))
        payloads = _request(client, params, url=ENSEMBLE_URL, weight=weight)
        if len(payloads) != len(batch):
            raise OpenMeteoError(f"{spec.id}: expected {len(batch)} locations, got {len(payloads)}")
        for r, p in zip(batch, payloads):
            out[r.id] = parse_members(p, spec.id, r.id)
        record(usage, weight, "ensemble")
    return out
