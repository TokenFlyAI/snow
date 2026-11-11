"""Small thermodynamic helpers (vectorised with numpy)."""
from __future__ import annotations

import numpy as np

PSYCHROMETRIC_A = 6.62e-4  # 1/degC, ventilated psychrometer over water


def sat_vapor_pressure(t_c):
    """Saturation vapour pressure over water in hPa (Bolton 1980)."""
    t_c = np.asarray(t_c, dtype=float)
    return 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))


def pressure_at(z_m):
    """Standard-atmosphere pressure (hPa) at height z (m)."""
    z_m = np.asarray(z_m, dtype=float)
    return 1013.25 * np.power(np.clip(1.0 - 2.25577e-5 * z_m, 1e-6, None), 5.25588)


def wet_bulb(t_c, rh_pct, p_hpa):
    """Wet-bulb temperature (degC) by bisection on the psychrometric equation.

        e = es(Tw) - A * p * (T - Tw)

    Accurate to ~0.01 degC; NaN in gives NaN out.
    """
    t = np.asarray(t_c, dtype=float)
    rh = np.clip(np.asarray(rh_pct, dtype=float), 1.0, 100.0)
    p = np.asarray(p_hpa, dtype=float)
    t, rh, p = np.broadcast_arrays(t, rh, p)
    e = rh / 100.0 * sat_vapor_pressure(t)
    lo = t - 45.0
    hi = t.copy()
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        f = sat_vapor_pressure(mid) - PSYCHROMETRIC_A * p * (t - mid) - e
        too_warm = f > 0
        hi = np.where(too_warm, mid, hi)
        lo = np.where(too_warm, lo, mid)
    tw = 0.5 * (lo + hi)
    return np.where(np.isfinite(t) & np.isfinite(rh) & np.isfinite(p), tw, np.nan)


def wind_chill(t_c, wind_kmh):
    """NWS/Environment Canada wind chill (degC). Returns T where the formula does not apply."""
    t = np.asarray(t_c, dtype=float)
    v = np.asarray(wind_kmh, dtype=float)
    v16 = np.power(np.clip(v, 0.0, None), 0.16)
    wc = 13.12 + 0.6215 * t - 11.37 * v16 + 0.3965 * t * v16
    return np.where((t <= 10.0) & (v > 4.8), np.minimum(wc, t), t)
