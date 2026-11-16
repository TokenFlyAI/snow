"""obs/{resort_id}.json: what the nearby stations measured over the last two weeks (design doc A1).

Published with the forecast so the page can show "what actually fell" next to "what we said".
Only resorts with a station in data/stations.yaml (scripts/match_stations.py) get a file. Sources:
SNOTEL (pipeline/verify/obs_snotel.py) and SLF IMIS (obs_slf.py, ids "SLF:<code>"); each is fetched
on its own, so one failing source keeps the other. Older days are kept in the archive.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from ..config import SCHEMA_VERSION
from ..verify import obs_slf, obs_snotel
from ..verify.obs import ski_days, unusable, window_edges

log = logging.getLogger(__name__)

OBS_DAYS = 14
MARGIN_H = 6                    # extra hours before the first window for the median filters

Fetcher = Callable[[list[str], dict[str, float], datetime, datetime], dict]


def source_of(sid: str) -> str:
    return obs_slf.SOURCE if sid.startswith(obs_slf.PREFIX) else obs_snotel.SOURCE


def fetch_all(ids: list[str], offsets: dict[str, float], start: datetime, end: datetime) -> dict:
    groups: dict = {}
    for sid in ids:
        groups.setdefault(obs_slf.fetch if sid.startswith(obs_slf.PREFIX) else obs_snotel.fetch, []).append(sid)
    out = {}
    for fn, sub in groups.items():
        try:
            out.update(fn(sub, offsets, start, end))
        except Exception as e:                      # noqa: BLE001  one source down must not sink the other
            log.warning("observations from %s failed: %s", source_of(sub[0]), e)
    return out


def _stamp(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_obs_docs(resorts: list, stations_by_resort: dict[str, list[dict]], now: datetime,
                   fetch: Optional[Fetcher] = None, past: Optional[dict] = None) -> dict[str, dict]:
    """resort id -> obs document, for the resorts with stations. Raises when nothing could be fetched.
    `past`: archived rows by (resort id, station, date), used for days the live fetch did not cover."""
    fetch = fetch or fetch_all
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
            days = [d.as_dict() for d in ski_days(ser, r.timezone, days_of[r.id], now)]
            for i, d in enumerate(days):
                old = (past or {}).get((r.id, s["triplet"], d["date"]))
                if unusable(d) and old and d["complete"]:
                    days[i] = {"date": d["date"], "complete": True} | {k: v for k, v in old.items() if k in d}
            sts.append({k: s.get(k) for k in ("triplet", "name", "lat", "lon", "elevation_m", "km", "dz_m", "grade")}
                       | {"source": source_of(s["triplet"]), "days": days})
        if sts:
            docs[r.id] = {"schema_version": SCHEMA_VERSION, "resort_id": r.id, "generated_at": _stamp(now),
                          "source": "; ".join(sorted({x["source"] for x in sts})), "timezone": r.timezone,
                          "units": {"precip": "mm", "snow": "cm", "depth": "cm", "temp": "degC"},
                          "notes": "Ski day = 16:00 the day before -> 16:00 local; night = 16:00 -> 08:00. "
                                   "snow_cm is a lower bound (new snow settles); days flagged depth_fell are "
                                   "not usable for new snow. Method: pipeline/verify/obs.py.",
                          "stations": sts}
    log.info("observations: %d resorts, %d of %d stations returned data", len(docs), len(series), len(offsets))
    return docs
