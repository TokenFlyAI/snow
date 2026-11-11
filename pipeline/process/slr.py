"""Snow-to-liquid ratio (SLR) with the Kuchera method.

Kuchera uses the warmest temperature in the column between the surface and
500 hPa (Tmax, kelvin):

    Tmax >  271.16 K :  SLR = 12 + 2 * (271.16 - Tmax)
    Tmax <= 271.16 K :  SLR = 12 +     (271.16 - Tmax)

That gives ~5-8:1 near freezing (heavy, wet snow) and 15-20:1 in cold air
(dry powder), instead of a fixed 10:1.

Two practical limits on top of the textbook formula:
- the ratio is capped at 25:1 (Kuchera keeps growing in very cold air, real
  snow does not);
- strong wind breaks crystals and packs the snow, so the ratio is reduced by
  up to 35 % between 25 and 90 km/h (`wind_factor`). The March 2024 Sierra
  blizzard backtest (tests/test_backtest.py) shows why: pure Kuchera turns
  ~270 mm of liquid into 4-5 m of snow at 2440 m.
Both are tunable heuristics until phase 4 verification replaces them.
"""
from __future__ import annotations

import numpy as np

KUCHERA_PIVOT_K = 271.16
SLR_MIN = 3.0
SLR_MAX = 25.0

WIND_CALM_KMH = 25.0
WIND_FULL_KMH = 90.0
WIND_MAX_REDUCTION = 0.35

POWDER_SLR = 14.0
HEAVY_SLR = 9.0


def kuchera_slr(tmax_k) -> np.ndarray:
    tmax = np.asarray(tmax_k, dtype=float)
    diff = KUCHERA_PIVOT_K - tmax
    slr = np.where(tmax > KUCHERA_PIVOT_K, 12.0 + 2.0 * diff, 12.0 + diff)
    return np.where(np.isfinite(tmax), np.clip(slr, SLR_MIN, SLR_MAX), np.nan)


def wind_factor(wind_kmh) -> np.ndarray:
    """Multiplier (0.65..1) on the SLR for wind compaction. NaN wind -> 1."""
    w = np.asarray(wind_kmh, dtype=float)
    x = np.clip((w - WIND_CALM_KMH) / (WIND_FULL_KMH - WIND_CALM_KMH), 0.0, 1.0)
    return np.where(np.isfinite(w), 1.0 - WIND_MAX_REDUCTION * x, 1.0)


def column_tmax_c(z: np.ndarray | None, t: np.ndarray | None, z_surface: float, t_surface) -> np.ndarray:
    """Warmest temperature (degC) from the surface up to the top profile level."""
    t_surface = np.asarray(t_surface, dtype=float)
    if z is None or t is None:
        return t_surface
    above = np.where(z > z_surface, t, -np.inf)       # ignore levels below ground
    above = np.where(np.isfinite(above) | (above == -np.inf), above, -np.inf)
    return np.maximum(t_surface, above.max(axis=0))


def slr_at(z: np.ndarray | None, t: np.ndarray | None, z_surface: float, t_surface,
           wind_kmh=None) -> np.ndarray:
    slr = kuchera_slr(column_tmax_c(z, t, z_surface, t_surface) + 273.15)
    if wind_kmh is not None:
        slr = np.maximum(slr * wind_factor(wind_kmh), SLR_MIN)
    return slr


def snowfall_cm(precip_mm, frac_snow, slr) -> np.ndarray:
    """Snow depth (cm) = liquid (mm) x snow fraction x SLR / 10.

    In the melting layer the flakes are partly melted and pack denser, so the
    effective ratio is reduced towards 60 % as the snow fraction goes to zero.
    """
    p = np.asarray(precip_mm, dtype=float)
    f = np.asarray(frac_snow, dtype=float)
    s = np.asarray(slr, dtype=float)
    eff = s * (0.6 + 0.4 * f)
    return p * f * eff / 10.0


def snow_quality(slr: float) -> str:
    """powder / packed / heavy from the precipitation-weighted SLR."""
    if not np.isfinite(slr):
        return "none"
    if slr >= POWDER_SLR:
        return "powder"
    if slr >= HEAVY_SLR:
        return "packed"
    return "heavy"
