"""Vertical-profile utilities.

A profile is a pair of (n_levels, n_time) arrays: heights `z` (m, lowest
level first) and a quantity `v` on those levels.
"""
from __future__ import annotations

import numpy as np

STD_LAPSE = 6.5e-3  # degC per m


def interp_at(z: np.ndarray, v: np.ndarray, z_target) -> np.ndarray:
    """Linear interpolation of v to height z_target for every time step.

    Extrapolates below the lowest / above the highest level using the gradient
    of the nearest layer. Columns containing NaN return NaN.
    """
    z = np.asarray(z, dtype=float)
    v = np.asarray(v, dtype=float)
    n_lev, n_t = z.shape
    zt = np.broadcast_to(np.asarray(z_target, dtype=float), (n_t,))
    out = np.full(n_t, np.nan)
    ok = np.isfinite(z).all(axis=0) & np.isfinite(v).all(axis=0) & np.isfinite(zt)
    if not ok.any() or n_lev < 2:
        return out
    zz, vv, tt = z[:, ok], v[:, ok], zt[ok]
    # index of the layer [k, k+1] to use: clamp so we extrapolate at the ends
    k = (zz[1:] <= tt).sum(axis=0)
    k = np.clip(k, 0, n_lev - 2)
    cols = np.arange(zz.shape[1])
    z0, z1 = zz[k, cols], zz[k + 1, cols]
    v0, v1 = vv[k, cols], vv[k + 1, cols]
    dz = np.where(np.abs(z1 - z0) < 1e-6, 1e-6, z1 - z0)
    out[ok] = v0 + (v1 - v0) * (tt - z0) / dz
    return out


def crossing_height(z: np.ndarray, v: np.ndarray, threshold: float,
                    below_gradient: float = STD_LAPSE) -> np.ndarray:
    """Height of the *highest* level where v drops through `threshold` going up.

    Searching from the top matters for snow: it has to survive every warm layer
    above the ground, so the uppermost melting level is the relevant one.

    - Whole column colder than threshold: extrapolate below the lowest level
      with `below_gradient` (v increases downward by that much per metre).
    - Top level warmer than threshold: return the top level height.
    """
    z = np.asarray(z, dtype=float)
    v = np.asarray(v, dtype=float)
    n_lev, n_t = z.shape
    out = np.full(n_t, np.nan)
    ok = np.isfinite(z).all(axis=0) & np.isfinite(v).all(axis=0)
    for j in np.flatnonzero(ok):
        zc, vc = z[:, j], v[:, j]
        if vc[-1] >= threshold:
            out[j] = zc[-1]
            continue
        found = False
        for k in range(n_lev - 2, -1, -1):
            if vc[k] >= threshold:  # crossing between k (warm) and k+1 (cold)
                frac = (vc[k] - threshold) / (vc[k] - vc[k + 1])
                out[j] = zc[k] + frac * (zc[k + 1] - zc[k])
                found = True
                break
        if not found:
            out[j] = zc[0] - (threshold - vc[0]) / below_gradient
    return out
