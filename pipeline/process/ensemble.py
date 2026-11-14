"""Ensemble post-processing: member ski-day totals -> percentiles and probabilities.

Two stages, so that the expensive download is only needed once a day:

1. `raw_document()` reduces every member's hourly snowfall to ski-day totals
   and stores them untouched (cm at Open-Meteo's fixed 7:1 ratio, mid-mountain
   elevation) in `ens/{resort}.json`.
2. `Pool` + `calibrate()` + the `*_stats()` functions turn those totals into
   what is published. This runs every time a resort document is built, so the
   percentiles always match the current deterministic blend.

Why calibrate: global ensembles run at 25-50 km and smooth the mountains away,
so their raw amounts are biased against the high-resolution blend. Members are
first rescaled with the blend's snow-to-liquid ratio of the day, then multiplied
by one factor per resort that makes the ensemble-mean total of the next ten ski
days equal the blend's total. Spread and timing stay those of the ensemble.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

from ..config import ENSEMBLE_BY_ID, SCHEMA_VERSION
from . import aggregate

MIN_MEMBERS = 8                       # below this no percentile / probability is published
DAY_THRESHOLDS_CM = (2.5, 15.0)       # chance of at least 1 in / 6 in on a ski day
WEEK_THRESHOLDS_CM = (15.0, 30.0, 60.0)
OM_SNOW_RATIO = 7.0                   # Open-Meteo snowfall: 0.7 cm per mm of water
SLR_LIMITS = (5.0, 20.0)
FACTOR_LIMITS = (0.5, 2.5)
MIN_CALIBRATION_CM = 5.0              # below this total the factor would be noise
DAY_HOURS = 24


# --------------------------------------------------------------------------- stage 1: raw member totals
def member_day_totals(time_utc: np.ndarray, members: np.ndarray, tz_name: str, dates: Sequence[date],
                      min_coverage: float = 0.8) -> np.ndarray:
    """(n_members, n_days) snowfall per ski day; NaN where a member covers too little of the day."""
    members = np.asarray(members, dtype=float)
    out = np.full((members.shape[0], len(dates)), np.nan)
    if members.size == 0 or not len(dates):
        return out
    idx = aggregate.index_hours(time_utc, tz_name)
    day_no = np.array([(d - dates[0]).days for d in idx.ski_date])
    finite = np.isfinite(members)
    for k in range(len(dates)):
        mask = day_no == k
        if not mask.any():
            continue
        n_ok = finite[:, mask].sum(axis=1)
        tot = np.where(finite[:, mask], members[:, mask], 0.0).sum(axis=1)
        out[:, k] = np.where(n_ok / DAY_HOURS >= min_coverage, tot, np.nan)
    return out


def raw_document(resort_id: str, elevation_m: int, start: date, n_days: int, tz_name: str,
                 data: Mapping[str, tuple[np.ndarray, np.ndarray]], now: datetime) -> dict:
    """The cacheable `ens/{resort}.json`. `data` maps model id -> (time_utc, members)."""
    dates = [start + timedelta(days=k) for k in range(n_days)]
    models = {}
    for mid, (t, members) in data.items():
        tot = member_day_totals(t, members, tz_name, dates)
        keep = np.isfinite(tot).any(axis=1)
        if not keep.any():
            continue
        last = int(np.flatnonzero(np.isfinite(tot).any(axis=0)).max()) + 1
        spec = ENSEMBLE_BY_ID.get(mid)
        models[mid] = {
            "label": spec.label if spec else mid,
            "weight": spec.weight if spec else 1.0,
            "members": int(keep.sum()),
            "daily": [[None if not np.isfinite(x) else round(float(x), 1) for x in row[:last]] for row in tot[keep]],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resort_id": resort_id, "elevation_m": elevation_m,
        "unit": "cm per ski day at a fixed 7:1 snow ratio (raw Open-Meteo snowfall)",
        "start_date": start.isoformat(), "models": models,
    }


# --------------------------------------------------------------------------- stage 2: pooled distribution
@dataclass
class Pool:
    """All members of all ensembles on a common list of ski dates."""
    dates: list[date]
    values: np.ndarray        # (n_members, n_days), cm
    weights: np.ndarray       # (n_members,): model weight / members of that model
    model_of: list[str]
    labels: dict[str, str]

    @classmethod
    def from_raw(cls, raw: Optional[dict], dates: Sequence[date]) -> "Pool":
        dates = list(dates)
        rows, weights, model_of, labels = [], [], [], {}
        if raw and raw.get("models"):
            start = date.fromisoformat(raw["start_date"])
            shift = (dates[0] - start).days if dates else 0
            for mid, m in raw["models"].items():
                n = len(m["daily"])
                if not n:
                    continue
                labels[mid] = m.get("label", mid)
                for series in m["daily"]:
                    row = np.full(len(dates), np.nan)
                    for k in range(len(dates)):
                        j = k + shift
                        if 0 <= j < len(series) and series[j] is not None:
                            row[k] = series[j]
                    rows.append(row)
                    weights.append(float(m.get("weight", 1.0)) / n)
                    model_of.append(mid)
        values = np.stack(rows) if rows else np.empty((0, len(dates)))
        return cls(dates, values, np.array(weights, dtype=float), model_of, labels)

    @property
    def n_members(self) -> int:
        return int(self.values.shape[0])

    def models_on(self, days: Iterable[int]) -> list[str]:
        days = list(days)
        seen: list[str] = []
        for i, mid in enumerate(self.model_of):
            if mid not in seen and days and np.isfinite(self.values[i, days]).any():
                seen.append(mid)
        return seen


def weighted_quantiles(values: Sequence[float], weights: Sequence[float], qs: Sequence[float]) -> list[float]:
    """Quantiles of a weighted sample (same definition as blend.weighted_quantile)."""
    v, w = np.asarray(values, dtype=float), np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & (w > 0)
    v, w = v[ok], w[ok]
    if v.size == 0:
        return [float("nan")] * len(qs)
    if v.size == 1:
        return [float(v[0])] * len(qs)
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    cdf = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [float(np.interp(q, cdf, v)) for q in qs]


def prob_at_least(values: Sequence[float], weights: Sequence[float], threshold: float) -> float:
    """Weighted share of members with at least `threshold`; NaN members do not vote."""
    v, w = np.asarray(values, dtype=float), np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & (w > 0)
    if not ok.any():
        return float("nan")
    return float(w[ok & (v >= threshold)].sum() / w[ok].sum())


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    v, w = np.asarray(values, dtype=float), np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & (w > 0)
    return float((v[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else float("nan")


@dataclass
class Stats:
    p10: float
    p50: float
    p90: float
    mean: float
    prob: dict[float, float]
    n_members: int

    @property
    def ok(self) -> bool:
        return self.n_members >= MIN_MEMBERS and bool(np.isfinite(self.p50))


def stats(values: Sequence[float], weights: Sequence[float], thresholds: Sequence[float]) -> Stats:
    v = np.asarray(values, dtype=float)
    p10, p50, p90 = weighted_quantiles(v, weights, (0.1, 0.5, 0.9))
    return Stats(p10, p50, p90, weighted_mean(v, weights),
                 {t: prob_at_least(v, weights, t) for t in thresholds}, int(np.isfinite(v).sum()))


def window_totals(values: np.ndarray, days: Sequence[int], min_coverage: float = 0.85,
                  fill: Optional[Mapping[int, float]] = None) -> np.ndarray:
    """Per-member total over several ski days.

    A member must cover `min_coverage` of the days; the days it misses are
    filled with its own average (so ECMWF's 15 days still count in a 16-day
    total). `fill` supplies a known value for a day no member covers (today,
    for resorts east of the Atlantic, whose ski day started before the run).
    """
    days = [d for d in days if 0 <= d < values.shape[1]]
    if not days or values.shape[0] == 0:
        return np.full(values.shape[0], np.nan)
    sub = values[:, days].copy()
    if fill:
        for j, d in enumerate(days):
            if d in fill and np.isfinite(fill[d]):
                sub[:, j] = np.where(np.isfinite(sub[:, j]), sub[:, j], fill[d])
    ok = np.isfinite(sub)
    n_ok = ok.sum(axis=1)
    tot = np.where(ok, sub, 0.0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        scaled = tot * len(days) / n_ok
    return np.where(n_ok / len(days) >= min_coverage, scaled, np.nan)


# --------------------------------------------------------------------------- calibration against the blend
@dataclass
class Calibration:
    factor: float
    slr_default: float
    n_days: int
    blend_cm: float
    ensemble_cm: float


def calibrate(pool: Pool, slr_by_day: Sequence[float], blend_by_day: Sequence[float]) -> tuple[np.ndarray, Calibration]:
    """Rescale raw member totals (7:1) to the blend's snow ratio and amount.

    slr_by_day / blend_by_day are aligned with pool.dates; entries beyond the
    deterministic horizon are NaN (or missing) and fall back to the mean SLR.
    """
    n_days = len(pool.dates)
    slr = np.full(n_days, np.nan)
    slr[:min(n_days, len(slr_by_day))] = np.asarray(slr_by_day, dtype=float)[:n_days]
    with np.errstate(invalid="ignore"):
        default = float(np.nanmean(slr)) if np.isfinite(slr).any() else 10.0
    default = float(np.clip(default, *SLR_LIMITS))
    slr = np.clip(np.where(np.isfinite(slr), slr, default), *SLR_LIMITS)
    values = pool.values * (slr / OM_SNOW_RATIO)[None, :]

    blend = np.full(n_days, np.nan)
    blend[:min(n_days, len(blend_by_day))] = np.asarray(blend_by_day, dtype=float)[:n_days]
    mean = np.array([weighted_mean(values[:, k], pool.weights) for k in range(n_days)]) if pool.n_members else np.full(n_days, np.nan)
    both = np.isfinite(blend) & np.isfinite(mean)
    b, e = float(blend[both].sum()), float(mean[both].sum())
    factor = 1.0
    if both.sum() >= 3 and b >= MIN_CALIBRATION_CM and e >= MIN_CALIBRATION_CM:
        factor = float(np.clip(b / e, *FACTOR_LIMITS))
    return values * factor, Calibration(round(factor, 2), round(default, 1), int(both.sum()), round(b, 1), round(e, 1))


def level_ratio(level_total: float, mid_total: float, lo: float = 0.0, hi: float = 2.5) -> float:
    """How much more / less snow another elevation gets than mid-mountain, from the blend."""
    if not (np.isfinite(level_total) and np.isfinite(mid_total)) or mid_total < 1.0:
        return 1.0
    return float(np.clip(level_total / mid_total, lo, hi))
