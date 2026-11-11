"""Ski-day aggregation.

Skiers care about "how much fell overnight" and "how much falls while I'm
riding", so a ski day D is split in two windows of resort-local time:

    night:  16:00 (D-1)  ->  08:00 D     (lifts closed: tomorrow's fresh snow)
    day:    08:00 D      ->  16:00 D

Open-Meteo hourly accumulations are stamped at the END of the hour, so the
value at 17:00 covers 16:00-17:00 and belongs to the night window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from ..config import DAY_START_H, NIGHT_START_H


@dataclass
class HourIndex:
    ski_date: list[date]      # ski day each hourly value belongs to
    cal_date: list[date]      # local calendar date of the interval start
    is_night: np.ndarray      # bool
    local_start: list[datetime]


def _to_datetime(t64: np.datetime64) -> datetime:
    return datetime.fromtimestamp(int(t64.astype("datetime64[s]").astype(np.int64)), tz=timezone.utc)


def index_hours(time_utc: np.ndarray, tz_name: str) -> HourIndex:
    tz = ZoneInfo(tz_name)
    ski, cal, night, starts = [], [], [], []
    for t in time_utc:
        start = (_to_datetime(t) - timedelta(hours=1)).astimezone(tz)
        h = start.hour
        d = start.date()
        if h >= NIGHT_START_H:
            ski.append(d + timedelta(days=1))
            night.append(True)
        elif h < DAY_START_H:
            ski.append(d)
            night.append(True)
        else:
            ski.append(d)
            night.append(False)
        cal.append(d)
        starts.append(start)
    return HourIndex(ski, cal, np.array(night, dtype=bool), starts)


def window_sum(values: np.ndarray, mask: np.ndarray, min_coverage: float = 0.75) -> float:
    """Sum of values inside mask; NaN when too few hours are available."""
    n = int(mask.sum())
    if n == 0:
        return float("nan")
    v = values[mask]
    ok = np.isfinite(v)
    if ok.sum() / n < min_coverage:
        return float("nan")
    return float(v[ok].sum())


def window_stat(values: np.ndarray, mask: np.ndarray, fn, min_coverage: float = 0.5) -> float:
    n = int(mask.sum())
    if n == 0:
        return float("nan")
    v = values[mask]
    ok = np.isfinite(v)
    if ok.sum() / n < min_coverage:
        return float("nan")
    return float(fn(v[ok]))


def day_masks(idx: HourIndex, d: date) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(night, day, calendar-day) boolean masks for ski day d."""
    ski = np.array([s == d for s in idx.ski_date], dtype=bool)
    cal = np.array([c == d for c in idx.cal_date], dtype=bool)
    return ski & idx.is_night, ski & ~idx.is_night, cal
