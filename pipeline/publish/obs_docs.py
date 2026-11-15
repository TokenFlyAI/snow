"""obs/{resort_id}.json: what the nearby stations measured over the last two weeks (design doc A1).

Published with the forecast so the page can show "what actually fell" next to "what we said".
Only resorts with a station in data/stations.yaml (scripts/match_stations.py) get a file. Older
observations are not kept here: AWDB serves the full history, so scoring (A3) re-reads it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from ..config import SCHEMA_VERSION
from ..verify import obs_snotel
from ..verify.obs import ski_days, window_edges

log = logging.getLogger(__name__)

OBS_DAYS = 14
MARGIN_H = 6                    # extra hours before the first window for the median filters

Fetcher = Callable[[list[str], dict[str, float], datetime, datetime], dict]


def _stamp(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_obs_docs(resorts: list, stations_by_resort: dict[str, list[dict]], now: datetime,
                   fetch: Optional[Fetcher] = None) -> dict[str, dict]:
    """resort id -> obs document, for the resorts with stations. Raises when nothing could be fetched."""
    fetch = fetch or obs_snotel.fetch
    wanted = [r for r in resorts if stations_by_resort.get(r.id)]
    if not wanted:
        return {}
    days_of = {}
    first = None
    for r in wanted:
        today = now.astimezone(ZoneInfo(r.timezone)).date()
        if now.astimezone(ZoneInfo(r.timezone)).hour >= 16:
            today += timedelta(days=1)                 # after lifts close the next ski day has begun
        dates = [today - timedelta(days=k) for k in range(OBS_DAYS - 1, -1, -1)]
        days_of[r.id] = dates
        t0 = window_edges(dates[0], r.timezone)[0]
        first = t0 if first is None or t0 < first else first
    start = (first - timedelta(hours=MARGIN_H)).replace(minute=0, second=0, microsecond=0)
    end = now.replace(minute=0, second=0, microsecond=0)
    offsets = {s["triplet"]: float(s.get("utc_offset_h", -8.0)) for r in wanted for s in stations_by_resort[r.id]}
    series = fetch(sorted(offsets), offsets, start, end)
    if not series:
        raise RuntimeError("no station data")

    docs = {}
    for r in wanted:
        sts = []
        for s in stations_by_resort[r.id]:
            ser = series.get(s["triplet"])
            if ser is None:
                continue
            days = ski_days(ser, r.timezone, days_of[r.id], now)
            sts.append({k: s.get(k) for k in ("triplet", "name", "lat", "lon", "elevation_m", "km", "dz_m", "grade")}
                       | {"days": [d.as_dict() for d in days]})
        if sts:
            docs[r.id] = {"schema_version": SCHEMA_VERSION, "resort_id": r.id, "generated_at": _stamp(now),
                          "source": obs_snotel.SOURCE, "timezone": r.timezone,
                          "units": {"precip": "mm", "snow": "cm", "depth": "cm", "temp": "degC"},
                          "notes": "Ski day = 16:00 the day before -> 16:00 local; night = 16:00 -> 08:00. "
                                   "snow_cm is a lower bound (new snow settles); days flagged depth_fell are "
                                   "not usable for new snow. Method: pipeline/verify/obs.py.",
                          "stations": sts}
    log.info("observations: %d resorts, %d of %d stations returned data", len(docs), len(series), len(offsets))
    return docs
