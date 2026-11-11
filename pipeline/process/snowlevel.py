"""Freezing level, snow level and precipitation type.

Snow level follows the NWS/NBM convention: the height where the wet-bulb
temperature is +0.5 degC. Falling snow cools the air by melting and
evaporation, so it survives below the 0 degC isotherm; the wet-bulb
profile captures that, and dry air pushes the snow level further down.
Without humidity we fall back to "freezing level minus 300 m".
"""
from __future__ import annotations

import numpy as np

from .profile import crossing_height
from .thermo import wet_bulb

SNOW_LEVEL_TW = 0.5        # degC wet-bulb
FALLBACK_OFFSET_M = 300.0  # snow level below the 0 degC isotherm when no humidity
MELT_DEPTH_M = 300.0       # all snow at the snow level -> all rain this far below
MOIST_LAPSE = 5.5e-3       # degC per m, used to extrapolate wet-bulb from the surface

SNOW, MIX, RAIN = 0, 1, 2


def freezing_level(z: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Height (m) of the highest 0 degC isotherm."""
    return crossing_height(z, t, 0.0)


def wet_bulb_profile(t: np.ndarray, rh: np.ndarray, p_levels) -> np.ndarray:
    p = np.asarray(p_levels, dtype=float)[:, None]
    return wet_bulb(t, rh, p)


def snow_level(z: np.ndarray, t: np.ndarray, rh: np.ndarray | None, p_levels) -> np.ndarray:
    """Snow level (m) from a pressure-level profile; never above the freezing level."""
    fzl = freezing_level(z, t)
    sl = np.full(fzl.shape, np.nan)
    if rh is not None:
        tw = wet_bulb_profile(t, rh, p_levels)
        sl = crossing_height(z, tw, SNOW_LEVEL_TW, below_gradient=MOIST_LAPSE)
    sl = np.where(np.isfinite(sl), sl, fzl - FALLBACK_OFFSET_M)
    return np.minimum(sl, fzl)


def snow_level_from_surface(t_c, rh_pct, z_surface: float, p_hpa) -> np.ndarray:
    """Snow level estimated from surface wet-bulb only (models without profiles)."""
    tw = wet_bulb(t_c, rh_pct, p_hpa)
    return z_surface + (tw - SNOW_LEVEL_TW) / MOIST_LAPSE


def snow_fraction(z_m: float, snow_level_m) -> np.ndarray:
    """Fraction of precipitation falling as snow at height z (0..1)."""
    sl = np.asarray(snow_level_m, dtype=float)
    frac = (z_m - (sl - MELT_DEPTH_M)) / MELT_DEPTH_M
    return np.where(np.isfinite(sl), np.clip(frac, 0.0, 1.0), np.nan)


def precip_type(frac_snow) -> np.ndarray:
    """0 = snow, 1 = mixed, 2 = rain (int8; -1 where unknown)."""
    f = np.asarray(frac_snow, dtype=float)
    out = np.full(f.shape, -1, dtype=np.int8)
    out[f >= 0.8] = SNOW
    out[(f < 0.8) & (f > 0.2)] = MIX
    out[f <= 0.2] = RAIN
    return out
