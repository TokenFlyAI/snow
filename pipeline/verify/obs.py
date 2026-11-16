"""Observed ski days from hourly station readings (design doc A1), independent of the network.

Input: hourly instantaneous readings on a UTC grid, already in metric units:

    precip_mm   cumulative precipitation gauge (resets once a year, 1 Oct)
    swe_mm      snow water equivalent of the snowpack (snow pillow)
    depth_cm    snow depth
    temp_c      air temperature

Output: per ski day the same windows as the forecast (pipeline/process/aggregate.py), in resort
local time: night 16:00 (D-1) -> 08:00 D, day 08:00 -> 16:00 D.

How each number is made (checked on SNOTEL 784, Palisades, blizzard of 28 Feb - 5 Mar 2024):

- precipitation: the gauge jitters by up to +-2 in in a storm (antifreeze sloshing in wind), so the
  series is median-filtered (7 h), made non-decreasing (running maximum; a drop of more than 100 mm
  is the yearly reset) and read at the window edges. Window totals add up to the gauge's total.
  Gauges under-catch snow in wind, so this is a lower bound in storms.
- swe_gain: rises of the median-filtered (5 h) snow water equivalent with a dead band, so the
  +-0.1 in jitter does not add up; 0 when the gauge has less than 3 mm (as for new snow). Wind scour and melt make it lower than the gauge; it is the
  check on the gauge, not the liquid total.
- new snow: rises of the median-filtered (5 h) snow depth with a 2 in dead band, counted only
  when the gauge has at least 3 mm in the window (the depth sensor jitters by +-1 in on dry days).
  A lower bound: new snow settles while it falls. A day on which the depth fell by more than 5 cm while at least
  5 mm of precipitation fell is flagged "depth_fell" (the sensor or the wind, not the snowfall);
  scoring must skip its new-snow value.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np
import yaml

from ..config import DAY_START_H, NIGHT_START_H

PRECIP_MEDIAN_H = 7
STATE_MEDIAN_H = 5
PRECIP_RESET_MM = 100.0       # a drop this large in the gauge is the yearly reset, not noise
SWE_DEADBAND_MM = 0.15 * 25.4
DEPTH_DEADBAND_CM = 1.5 * 2.54     # integer inches: a 1 in dip is noise, 2 in is settling
EDGE_SEARCH_H = 3             # a missing reading at a window edge is taken from the nearest within 3 h
MIN_COVERAGE = 0.75
DEPTH_FELL_CM = 5.0
DEPTH_FELL_MIN_PRECIP_MM = 5.0
SNOW_MIN_PRECIP_MM = 3.0      # depth rises with less gauge precipitation than this are sensor jitter
RANGES = {"precip_mm": (0.0, 10_000.0), "swe_mm": (0.0, 10_000.0), "depth_cm": (0.0, 1_500.0), "temp_c": (-60.0, 50.0)}


@dataclass
class HourlySeries:
    """Hourly readings on a regular UTC grid: times[i] = start + i hours."""
    start: datetime                      # UTC, on the hour
    values: dict[str, np.ndarray]        # element -> float array, NaN = missing

    @property
    def n(self) -> int:
        return len(next(iter(self.values.values()))) if self.values else 0

    def index(self, t: datetime) -> int:
        return int(round((t - self.start).total_seconds() / 3600.0))


@dataclass
class ObsDay:
    date: str
    complete: bool                       # the window has ended
    precip_mm: Optional[float] = None
    precip_night_mm: Optional[float] = None
    swe_gain_mm: Optional[float] = None
    snow_cm: Optional[float] = None
    snow_night_cm: Optional[float] = None
    depth_cm: Optional[float] = None     # at the end of the window (or the latest reading)
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---- filters ------------------------------------------------------------------------------------

def clean(name: str, v: np.ndarray) -> np.ndarray:
    lo, hi = RANGES.get(name, (-np.inf, np.inf))
    v = np.asarray(v, dtype=float).copy()
    v[(v < lo) | (v > hi)] = np.nan
    return v


def rolling_median(v: np.ndarray, width: int) -> np.ndarray:
    """Centered running median ignoring NaN; NaN where fewer than half the window is valid."""
    half = width // 2
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        w = v[max(0, i - half): i + half + 1]
        w = w[np.isfinite(w)]
        if len(w) >= half + 1:
            out[i] = float(np.median(w))
    return out


def monotone(v: np.ndarray, reset: float = PRECIP_RESET_MM) -> np.ndarray:
    """Running maximum of a cumulative gauge; a drop larger than `reset` restarts it."""
    out = np.full(len(v), np.nan)
    top = np.nan
    for i, x in enumerate(v):
        if not np.isfinite(x):
            continue
        if not np.isfinite(top) or x > top or x < top - reset:
            top = x
        out[i] = top
    return out


def gain(v: np.ndarray, deadband: float) -> float:
    """Sum of rises; the reference only follows a fall larger than the dead band."""
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return float("nan")
    ref, total = v[0], 0.0
    for x in v[1:]:
        if x > ref:
            total += x - ref
            ref = x
        elif x < ref - deadband:
            ref = x
    return float(total)


def level_at(v: np.ndarray, i: int, search: int = EDGE_SEARCH_H) -> float:
    for d in range(search + 1):
        for j in (i - d, i + d):
            if 0 <= j < len(v) and np.isfinite(v[j]):
                return float(v[j])
    return float("nan")


def coverage(v: np.ndarray, i0: int, i1: int) -> float:
    i0, i1 = max(0, i0), min(len(v) - 1, i1)
    if i1 < i0:
        return 0.0
    return float(np.isfinite(v[i0: i1 + 1]).mean())


def _r(x: float, nd: int = 1) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


# ---- ski days -----------------------------------------------------------------------------------

def window_edges(d: date, tz: str) -> tuple[datetime, datetime, datetime]:
    """(start, night end, end) of ski day d in UTC."""
    z = ZoneInfo(tz)
    start = datetime.combine(d - timedelta(days=1), datetime.min.time(), z).replace(hour=NIGHT_START_H)
    mid = datetime.combine(d, datetime.min.time(), z).replace(hour=DAY_START_H)
    end = datetime.combine(d, datetime.min.time(), z).replace(hour=NIGHT_START_H)
    return tuple(t.astimezone(timezone.utc) for t in (start, mid, end))


def ski_days(series: HourlySeries, tz: str, dates: list[date], now: datetime) -> list[ObsDay]:
    v = {k: clean(k, a) for k, a in series.values.items()}
    nan = np.full(series.n, np.nan)
    prec = monotone(rolling_median(v.get("precip_mm", nan), PRECIP_MEDIAN_H))
    swe = rolling_median(v.get("swe_mm", nan), STATE_MEDIAN_H)
    depth = rolling_median(v.get("depth_cm", nan), STATE_MEDIAN_H)
    temp = v.get("temp_c", nan)
    out = []
    for d in dates:
        t0, tm, t1 = window_edges(d, tz)
        complete = t1 <= now
        i0, im = series.index(t0), series.index(tm)
        last = series.index(t1) if complete else int((now - series.start).total_seconds() // 3600)
        i1 = min(last, series.n - 1)
        day = ObsDay(date=d.isoformat(), complete=complete)
        if i0 < 0 or i1 <= i0:
            day.flags.append("no_data")
            out.append(day)
            continue

        if coverage(prec, i0, i1) >= MIN_COVERAGE:
            day.precip_mm = _r(max(0.0, level_at(prec, i1) - level_at(prec, i0)))
            if im <= i1:
                day.precip_night_mm = _r(max(0.0, level_at(prec, im) - level_at(prec, i0)))
        if coverage(swe, i0, i1) >= MIN_COVERAGE:
            day.swe_gain_mm = _r(gain(swe[i0: i1 + 1], SWE_DEADBAND_MM))
        if coverage(depth, i0, i1) >= MIN_COVERAGE:
            day.snow_cm = _r(gain(depth[i0: i1 + 1], DEPTH_DEADBAND_CM))
            if im <= i1:
                day.snow_night_cm = _r(gain(depth[i0: im + 1], DEPTH_DEADBAND_CM))
            day.depth_cm = _r(level_at(depth, i1), 0)
            net = level_at(depth, i1) - level_at(depth, i0)
            if net < -DEPTH_FELL_CM and (day.precip_mm or 0.0) >= DEPTH_FELL_MIN_PRECIP_MM:
                day.flags.append("depth_fell")
            if day.precip_mm is not None and day.precip_mm < SNOW_MIN_PRECIP_MM:
                day.snow_cm = 0.0
                if day.swe_gain_mm is not None:
                    day.swe_gain_mm = 0.0
            if day.precip_night_mm is not None and day.precip_night_mm < SNOW_MIN_PRECIP_MM:
                day.snow_night_cm = 0.0
        if coverage(temp, i0, i1) >= 0.5:
            w = temp[i0: i1 + 1]
            day.temp_min_c, day.temp_max_c = _r(np.nanmin(w)), _r(np.nanmax(w))
        if day.precip_mm is None and day.snow_cm is None:
            day.flags.append("gaps")
        out.append(day)
    return out


def unusable(day: dict) -> bool:
    """A ski day (ObsDay.as_dict()) with nothing measured: no data, or no precipitation and no depth."""
    flags = day.get("flags") or []
    return "no_data" in flags or "gaps" in flags


# ---- station list -------------------------------------------------------------------------------

def load_stations(path: Path | str) -> dict[str, list[dict]]:
    """data/stations.yaml -> resort id -> stations (best first)."""
    p = Path(path)
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {rid: list(sts or []) for rid, sts in (doc.get("resorts") or {}).items()}
