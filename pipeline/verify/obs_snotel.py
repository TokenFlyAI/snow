"""USDA NRCS SNOTEL hourly readings via the AWDB REST API (public domain, no key, not Open-Meteo).

    https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data

Hourly values are instantaneous readings stamped in the station's data time zone, a fixed UTC
offset that ignores daylight saving (dataTimeZone: -8 for the lower 48, -9 for Alaska; stored in
data/stations.yaml as utc_offset_h). Units: inches and degrees F.

Daily values (not used here) are the reading at the END of the day, which is why the ski-day
windows are rebuilt from hourly readings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import httpx
import numpy as np

from .obs import HourlySeries

log = logging.getLogger(__name__)

API = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
UA = {"User-Agent": "snow-forecast-pipeline/0.2 (+https://github.com/TokenFlyAI/snow)"}
ELEMENTS = {"PREC": ("precip_mm", lambda x: x * 25.4), "WTEQ": ("swe_mm", lambda x: x * 25.4),
            "SNWD": ("depth_cm", lambda x: x * 2.54), "TOBS": ("temp_c", lambda x: (x - 32.0) / 1.8)}
BATCH = 20                      # stations per request
SOURCE = "USDA NRCS SNOTEL (public domain)"


def parse(payload: list, offsets: dict[str, float], start: datetime, hours: int) -> dict[str, HourlySeries]:
    """AWDB /data response -> triplet -> hourly series on the UTC grid start .. start + hours - 1."""
    out = {}
    for st in payload or []:
        trip = st.get("stationTriplet")
        off = timedelta(hours=offsets.get(trip, -8.0))
        vals = {name: np.full(hours, np.nan) for name, _ in ELEMENTS.values()}
        for e in st.get("data") or []:
            code = (e.get("stationElement") or {}).get("elementCode")
            if code not in ELEMENTS:
                continue
            name, conv = ELEMENTS[code]
            for v in e.get("values") or []:
                x = v.get("value")
                if x is None:
                    continue
                t = datetime.strptime(v["date"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) - off
                i = int(round((t - start).total_seconds() / 3600.0))
                if 0 <= i < hours:
                    vals[name][i] = conv(float(x))
        out[trip] = HourlySeries(start=start, values=vals)
    return out


def fetch(triplets: Iterable[str], offsets: dict[str, float], start: datetime, end: datetime,
          client: Optional[httpx.Client] = None) -> dict[str, HourlySeries]:
    """Hourly readings of the stations between two UTC times (on the hour)."""
    triplets = sorted(set(triplets))
    hours = int((end - start).total_seconds() // 3600) + 1
    own = client is None
    client = client or httpx.Client(timeout=90.0, headers=UA, follow_redirects=True)
    out: dict[str, HourlySeries] = {}
    try:
        for k in range(0, len(triplets), BATCH):
            chunk = triplets[k: k + BATCH]
            # request in station time: the same fixed offset for a batch would be wrong for Alaska,
            # so ask a few hours wider and let parse() place each reading by its own station offset
            lo = (start + timedelta(hours=-10)).strftime("%Y-%m-%d %H:00")
            hi = (end + timedelta(hours=-7)).strftime("%Y-%m-%d %H:00")
            q = {"stationTriplets": ",".join(chunk), "elements": ",".join(ELEMENTS), "duration": "HOURLY",
                 "beginDate": lo, "endDate": hi}
            for attempt in range(3):
                try:
                    r = client.get(f"{API}/data", params=q)
                    r.raise_for_status()
                    out.update(parse(r.json(), offsets, start, hours))
                    break
                except (httpx.HTTPError, ValueError) as e:
                    log.warning("SNOTEL batch %d (attempt %d): %s", k // BATCH, attempt + 1, e)
            else:
                log.warning("SNOTEL batch %d dropped: %s", k // BATCH, ",".join(chunk))
    finally:
        if own:
            client.close()
    return out


def stations(client: Optional[httpx.Client] = None) -> list[dict]:
    """All active SNOTEL stations (AWDB /stations)."""
    own = client is None
    client = client or httpx.Client(timeout=120.0, headers=UA, follow_redirects=True)
    try:
        r = client.get(f"{API}/stations", params={"networkCds": "SNTL", "activeOnly": "true"})
        r.raise_for_status()
        return [s for s in r.json() if s.get("networkCode") == "SNTL"]
    finally:
        if own:
            client.close()
