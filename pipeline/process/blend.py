"""Multi-model blending, daily range and confidence.

The point value is a blend of the deterministic models with lead-time
dependent empirical weights (config.BLEND_WEIGHTS). A model with no value for
an hour simply drops out and the remaining weights are renormalised, so a
missing model never breaks the blend.

Range and confidence come from the ensembles (process/ensemble.py); the spread
between deterministic models is only the fallback for a day no ensemble covers.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from ..config import BLEND_WEIGHTS


def weights_for(model_ids: Sequence[str], lead_hours: np.ndarray) -> np.ndarray:
    """(n_models, n_time) weight matrix for the given lead times (hours)."""
    lead = np.asarray(lead_hours, dtype=float)
    w = np.zeros((len(model_ids), lead.shape[0]))
    lower = -np.inf
    for upper, table in BLEND_WEIGHTS:
        mask = (lead >= lower) & (lead < upper)
        for i, mid in enumerate(model_ids):
            w[i, mask] = table.get(mid, 0.0)
        lower = upper
    return w


def blend(stack: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """NaN-aware weighted mean over axis 0. All-missing columns give NaN."""
    stack = np.asarray(stack, dtype=float)
    ok = np.isfinite(stack)
    w = np.where(ok, weights, 0.0)
    wsum = w.sum(axis=0)
    # if every available model has zero weight, fall back to an unweighted mean
    fallback = (wsum == 0) & ok.any(axis=0)
    w = np.where(fallback[None, :] & ok, 1.0, w)
    wsum = w.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(ok, stack * w, 0.0).sum(axis=0) / wsum
    return np.where(wsum > 0, out, np.nan)


def weighted_quantile(values: Sequence[float], weights: Sequence[float], q: float) -> float:
    """Quantile of a weighted sample (linear interpolation between sample points)."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & (w > 0)
    v, w = v[ok], w[ok]
    if v.size == 0:
        return float("nan")
    if v.size == 1:
        return float(v[0])
    order = np.argsort(v)
    v, w = v[order], w[order]
    cdf = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, cdf, v))


LEVELS_OF_CONFIDENCE = ("low", "medium", "high")
DRY_CM = 2.5   # one inch: below this a day counts as "no real snow"


AGREE_REL = 0.5        # a member "agrees" when it is within +-50 % of the point value ...
AGREE_MIN_CM = 5.0     # ... or within 5 cm (2 in), whichever is wider
AGREE_HIGH, AGREE_MEDIUM = 0.50, 0.25


def ensemble_agreement(point: float, members: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted share of ensemble members whose daily total lands close to the point forecast.

    "Close" is +-50 % of the point value, at least +-5 cm. For a dry forecast this is
    simply the share of members with less than 5 cm.
    """
    v = np.asarray(members, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & (w > 0)
    if not ok.any() or not np.isfinite(point):
        return float("nan")
    tol = max(AGREE_REL * abs(point), AGREE_MIN_CM)
    return float(w[ok & (np.abs(v - point) <= tol)].sum() / w[ok].sum())


def ensemble_confidence(agreement: float, lead_days: float) -> str:
    """high / medium / low from the share of ensemble members that agree with the point value.

    Half or more: high. A quarter or more: medium. Less: low. The exact day of a storm
    is not predictable a week out, so from day 7 the answer is at most medium.
    """
    if not np.isfinite(agreement):
        return "low"
    level = 2 if agreement >= AGREE_HIGH else 1 if agreement >= AGREE_MEDIUM else 0
    if lead_days >= 7:
        level = min(level, 1)
    return LEVELS_OF_CONFIDENCE[level]


def model_spread_confidence(values: Sequence[float], weights: Sequence[float], lead_days: float) -> str:
    """Fallback when no ensemble covers the day: agreement between the deterministic models."""
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 2:
        level = 1 if ok.sum() == 1 else 0
    else:
        lo = weighted_quantile(v, weights, 0.1)
        hi = weighted_quantile(v, weights, 0.9)
        med = weighted_quantile(v, weights, 0.5)
        rel = (hi - lo) / max(med, DRY_CM)  # agreeing on "nothing" is high confidence
        level = 2 if rel < 0.6 else 1 if rel < 1.4 else 0
    if lead_days >= 6:
        level = min(level, 1)
    return LEVELS_OF_CONFIDENCE[level]


def daily_range(point: float, ens_low: float, ens_high: float,
                model_values: Sequence[float], model_weights: Sequence[float]) -> tuple[float, float, str]:
    """(low, high, source) for a daily total.

    The band is the ensemble's 10-90 % range when there is one, else the
    weighted 10-90 % range of the deterministic models. Either way it is
    widened to contain the published point value.
    """
    if np.isfinite(ens_low) and np.isfinite(ens_high):
        lo, hi, source = ens_low, ens_high, "ensemble"
    else:
        lo = weighted_quantile(model_values, model_weights, 0.1)
        hi = weighted_quantile(model_values, model_weights, 0.9)
        source = "models"
    if np.isfinite(point):
        lo = min(lo, point) if np.isfinite(lo) else point
        hi = max(hi, point) if np.isfinite(hi) else point
    return lo, hi, source
