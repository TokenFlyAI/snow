"""Elevation correction of 2 m temperature.

Model terrain is smoothed, so the grid-cell height rarely matches the
resort. We move the model's 2 m temperature from the grid height to the
target height using the lapse rate the model itself has in that layer
(from pressure-level temperatures), clamped to a physical range.
"""
from __future__ import annotations

import numpy as np

from .profile import interp_at

DEFAULT_LAPSE = 6.5   # degC per km, positive = cooling with height
MIN_LAPSE = 3.0
MAX_LAPSE = 9.8       # dry adiabatic
MIN_LAYER_M = 300.0   # never derive a lapse rate from a thinner layer


def layer_lapse(z: np.ndarray, t: np.ndarray, z_a: float, z_b: float,
                default: float = DEFAULT_LAPSE) -> np.ndarray:
    """Lapse rate (degC/km, positive = cooling upward) between two heights."""
    lo, hi = (z_a, z_b) if z_a <= z_b else (z_b, z_a)
    if hi - lo < MIN_LAYER_M:
        pad = (MIN_LAYER_M - (hi - lo)) / 2.0
        lo, hi = lo - pad, hi + pad
    t_lo = interp_at(z, t, lo)
    t_hi = interp_at(z, t, hi)
    gamma = -(t_hi - t_lo) / (hi - lo) * 1000.0
    gamma = np.where(np.isfinite(gamma), gamma, default)
    return np.clip(gamma, MIN_LAPSE, MAX_LAPSE)


def correct_temperature(t2m: np.ndarray, z_grid: float, z_target: float,
                        z: np.ndarray | None = None, t: np.ndarray | None = None,
                        lapse: np.ndarray | float | None = None):
    """Return (temperature at z_target, lapse rate used in degC/km).

    `lapse` overrides the profile (used for models without pressure levels).
    """
    t2m = np.asarray(t2m, dtype=float)
    if lapse is not None:
        gamma = np.clip(np.broadcast_to(np.asarray(lapse, dtype=float), t2m.shape), MIN_LAPSE, MAX_LAPSE)
        gamma = np.where(np.isfinite(gamma), gamma, DEFAULT_LAPSE)
    elif z is not None and t is not None and np.isfinite(z_grid):
        gamma = layer_lapse(z, t, z_grid, z_target)
    else:
        gamma = np.full(t2m.shape, DEFAULT_LAPSE)
    if not np.isfinite(z_grid):
        return t2m.copy(), gamma
    return t2m - gamma * (z_target - z_grid) / 1000.0, gamma
