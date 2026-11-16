"""SLF IMIS automatic stations (Switzerland) via the public SLF measurement API (CC BY 4.0, no key).

    https://measurement-api.slf.ch/public/api/imis/stations
    .../imis/station/{code}/measurements?period_in_days=1|3|7             every 30 min: HS (cm), TA_30MIN_MEAN (degC)
    .../imis/station/{code}/measurements-precipitation?period_in_days=N   every 10 min: RR_10MIN_SUM (mm);
                                                                          404 where the station has no gauge

Times are UTC. In data/stations.yaml these stations have ids "SLF:<code>" and utc_offset_h 0.
The live API goes back 7 days at most; older ski days of obs/{id}.json come from the archive.
Terms (https://www.slf.ch/en/services-and-products/slf-data-service): CC BY 4.0, a visible link to
www.slf.ch wherever the data is shown, and no load that could impair the service: one request per
station and quantity per run.
Without a gauge, new snow comes from the depth rise alone (pipeline/verify/obs.py skips the
"gauge saw >= 3 mm" check when there is no precipitation series).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Iterable, Optional

import httpx
import numpy as np

from .obs import HourlySeries

log = logging.getLogger(__name__)

API = "https://measurement-api.slf.ch/public/api/imis"
UA = {"User-Agent": "snow-forecast-pipeline/0.2 (+https://github.com/TokenFlyAI/snow)"}
PREFIX = "SLF:"
SOURCE = "WSL Institute for Snow and Avalanche Research SLF (CC BY 4.0)"
PERIODS = (1, 3, 7)             # the only values period_in_days accepts


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse(meas: list, prec: Optional[list], start: datetime, hours: int) -> HourlySeries:
    """Readings -> hourly series on the UTC grid start .. start + hours - 1.

    Depth and temperature: the reading on the hour. Precipitation: the running total of the 10-minute
    sums up to each hour (NaN everywhere when the station has no gauge)."""
    depth, temp, precip = (np.full(hours, np.nan) for _ in range(3))
    for m in meas or []:
        t = _t(m["measure_date"])
        if t.minute:
            continue
        i = int(round((t - start).total_seconds() / 3600.0))
        if 0 <= i < hours:
            if m.get("HS") is not None:
                depth[i] = float(m["HS"])
            if m.get("TA_30MIN_MEAN") is not None:
                temp[i] = float(m["TA_30MIN_MEAN"])
    if prec:
        sums = np.zeros(hours)
        seen = np.zeros(hours, dtype=bool)
        for p in prec:
            x = p.get("RR_10MIN_SUM")
            if x is None:
                continue
            # a 10-minute sum stamped hh:mm covers the 10 minutes before; it counts towards hour ceil(hh:mm)
            k = math.ceil((_t(p["measure_date"]) - start).total_seconds() / 3600.0 - 1e-9)
            if 0 <= k < hours:
                sums[k] += max(0.0, float(x))
                seen[k] = True
        if seen.any():
            first = int(np.argmax(seen))            # the hour before the first sum is the zero level
            precip[:] = np.cumsum(sums)
            precip[:max(0, first - 1)] = np.nan
    return HourlySeries(start=start, values={"precip_mm": precip, "depth_cm": depth, "temp_c": temp})


def _get(client: httpx.Client, path: str, days: int) -> Optional[list]:
    for attempt in range(3):
        try:
            r = client.get(f"{API}{path}", params={"period_in_days": days})
        except httpx.TransportError as e:
            log.warning("SLF %s: %s", path, e)
            continue
        if r.status_code == 404:
            return None
        if r.status_code >= 500 or r.status_code == 429:
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"SLF {path} failed")


def fetch(ids: Iterable[str], offsets: dict[str, float], start: datetime, end: datetime,
          client: Optional[httpx.Client] = None) -> dict[str, HourlySeries]:
    """Hourly series of the stations ("SLF:<code>") between two UTC times (on the hour)."""
    ids = sorted(set(ids))
    hours = int((end - start).total_seconds() // 3600) + 1
    need = math.ceil((datetime.now(timezone.utc) - start).total_seconds() / 86400) + 1
    days = next((p for p in PERIODS if p >= need), PERIODS[-1])
    own = client is None
    client = client or httpx.Client(timeout=60, headers=UA)
    out = {}
    try:
        for sid in ids:
            code = sid[len(PREFIX):]
            try:
                meas = _get(client, f"/station/{code}/measurements", days)
                prec = _get(client, f"/station/{code}/measurements-precipitation", days)
            except Exception as e:                       # one station must not sink the rest
                log.warning("SLF %s: %s", code, e)
                continue
            if meas:
                out[sid] = parse(meas, prec, start, hours)
    finally:
        if own:
            client.close()
    return out


def stations(client: Optional[httpx.Client] = None) -> list[dict]:
    """Snow stations (type SNOW_FLAT) as {id, name, lat, lon, elevation_m}."""
    own = client is None
    client = client or httpx.Client(timeout=60, headers=UA)
    try:
        r = client.get(f"{API}/stations")
        r.raise_for_status()
        return [{"id": PREFIX + s["code"], "name": s["label"], "lat": s["lat"], "lon": s["lon"],
                 "elevation_m": s["elevation"]} for s in r.json() if s.get("type") == "SNOW_FLAT"]
    finally:
        if own:
            client.close()
