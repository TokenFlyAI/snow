"""Multi-model blending.

Phase 1: lead-time dependent empirical weights (config.BLEND_WEIGHTS).
A model with no value for an hour simply drops out and the remaining
weights are renormalised, so a missing model never breaks the blend.
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


def confidence(values: Sequence[float], weights: Sequence[float], lead_days: float) -> str:
    """high / medium / low from model agreement on a daily snowfall total, capped by lead time.

    Phase 2 will add ensemble spread; for now this is model-to-model spread only.
    """
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 2:
        level = 1 if ok.sum() == 1 else 0
    else:
        lo = weighted_quantile(v, weights, 0.1)
        hi = weighted_quantile(v, weights, 0.9)
        med = weighted_quantile(v, weights, 0.5)
        rel = (hi - lo) / max(med, 2.5)  # 2.5 cm floor: agreeing on "nothing" is high confidence
        level = 2 if rel < 0.6 else 1 if rel < 1.4 else 0
    if lead_days >= 10:
        level = 0
    elif lead_days >= 6:
        level = min(level, 1)
    return ("low", "medium", "high")[level]
