"""Turn one model's raw series into resort-level quantities at base / mid / summit."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..config import PRESSURE_LEVELS
from ..ingest.open_meteo import ModelData
from ..resorts import LEVELS, Resort
from . import lapse as lapse_mod
from . import slr as slr_mod
from . import snowlevel
from .profile import interp_at
from .thermo import pressure_at

RIDGE_GUST_FACTOR = 1.3
# share of the ridge-top wind felt by the snow surface at each elevation
WIND_EXPOSURE = {"base": 0.5, "mid": 0.75, "summit": 1.0}


@dataclass
class Derived:
    model: str
    time: np.ndarray
    grid_elevation: float
    has_profile: bool
    precip: np.ndarray                              # mm per hour (liquid)
    snow_level: np.ndarray                          # m
    freezing_level: np.ndarray                      # m
    lapse: np.ndarray                               # degC/km used grid -> mid
    wind_summit: np.ndarray                         # km/h
    gust_summit: np.ndarray                         # km/h
    cloud: np.ndarray                               # %
    visibility: np.ndarray                          # m
    temp: dict[str, np.ndarray] = field(default_factory=dict)       # degC
    snow: dict[str, np.ndarray] = field(default_factory=dict)       # cm per hour
    rain: dict[str, np.ndarray] = field(default_factory=dict)       # mm per hour
    frac_snow: dict[str, np.ndarray] = field(default_factory=dict)  # 0..1
    slr: dict[str, np.ndarray] = field(default_factory=dict)


def _profile_ok(z: np.ndarray, t: np.ndarray) -> np.ndarray:
    return np.isfinite(z).all(axis=0) & np.isfinite(t).all(axis=0)


@dataclass
class Donor:
    """Consensus thermal structure from models that have pressure levels.

    Lent to models without a profile (e.g. NBM), which then contribute their
    precipitation and 2 m temperature while the snow level comes from here.
    """
    time: np.ndarray
    lapse: np.ndarray
    snow_level: np.ndarray
    freezing_level: np.ndarray

    def on(self, time: np.ndarray, a: np.ndarray) -> np.ndarray:
        if time.shape == self.time.shape and np.array_equal(time, self.time):
            return a
        out = np.full(time.shape, np.nan)
        pos = np.searchsorted(self.time, time)
        ok = pos < self.time.shape[0]
        ok[ok] &= self.time[pos[ok]] == time[ok]
        out[ok] = a[pos[ok]]
        return out


def derive(md: ModelData, resort: Resort, donor: Optional[Donor] = None) -> Derived:
    n = md.time.shape[0]
    z = md.level_stack("geopotential_height")
    t = md.level_stack("temperature")
    rh = md.level_stack("relative_humidity")
    wind_lv = md.level_stack("wind_speed")
    prof_ok = _profile_ok(z, t)
    rh_ok = np.isfinite(rh).all(axis=0)

    t2m = md.get("temperature_2m")
    rh2m = md.get("relative_humidity_2m")
    precip = md.get("precipitation")
    # judge the profile only over the hours this model actually covers
    covered = np.isfinite(precip)
    has_profile = bool(covered.any() and prof_ok[covered].mean() > 0.5)
    d_lapse = donor.on(md.time, donor.lapse) if donor else None
    d_sl = donor.on(md.time, donor.snow_level) if donor else np.full(n, np.nan)
    d_fzl = donor.on(md.time, donor.freezing_level) if donor else np.full(n, np.nan)
    z_grid = md.grid_elevation
    elev = resort.elevation_m

    # --- temperature at the three resort elevations ---------------------------
    temp: dict[str, np.ndarray] = {}
    used_lapse = np.full(n, lapse_mod.DEFAULT_LAPSE)
    for lv in LEVELS:
        z_lv = elev.get(lv)
        if has_profile:
            t_lv, g = lapse_mod.correct_temperature(t2m, z_grid, z_lv, z, t)
        else:
            t_lv, g = lapse_mod.correct_temperature(
                t2m, z_grid, z_lv, lapse=d_lapse if d_lapse is not None else lapse_mod.DEFAULT_LAPSE)
        temp[lv] = t_lv
        if lv == "mid":
            used_lapse = g

    # --- freezing level and snow level ----------------------------------------
    fzl = snowlevel.freezing_level(z, t) if has_profile else np.full(n, np.nan)
    fzl = np.where(np.isfinite(fzl), fzl, md.get("freezing_level_height"))
    fzl = np.where(np.isfinite(fzl), fzl, d_fzl)
    fzl_surface = z_grid + t2m / (used_lapse / 1000.0)
    fzl = np.where(np.isfinite(fzl), fzl, fzl_surface)

    sl = np.full(n, np.nan)
    if has_profile:
        sl = snowlevel.snow_level(z, t, rh if rh_ok[covered].mean() > 0.5 else None, PRESSURE_LEVELS)
    sl = np.where(np.isfinite(sl), sl, d_sl)
    sl_surface = snowlevel.snow_level_from_surface(t2m, rh2m, z_grid, pressure_at(z_grid))
    sl_surface = np.where(np.isfinite(sl_surface), sl_surface, fzl - snowlevel.FALLBACK_OFFSET_M)
    sl = np.where(np.isfinite(sl), sl, sl_surface)
    sl = np.minimum(sl, fzl)

    # --- wind at the summit ----------------------------------------------------
    w10 = md.get("wind_speed_10m")
    g10 = md.get("wind_gusts_10m")
    w_summit = interp_at(z, wind_lv, elev.summit) if has_profile else np.full(n, np.nan)
    w_summit = np.where(np.isfinite(w_summit), np.maximum(w_summit, 0.0), w10)
    # ridge-top gusts: free-air wind x 1.3, never below the model's own 10 m gust
    gust_summit = np.where(np.isfinite(w_summit), w_summit * RIDGE_GUST_FACTOR, g10)
    gust_summit = np.where(np.isfinite(g10), np.fmax(gust_summit, g10), gust_summit)

    # --- snow / rain at each elevation ----------------------------------------
    snow: dict[str, np.ndarray] = {}
    rain: dict[str, np.ndarray] = {}
    frac: dict[str, np.ndarray] = {}
    slr: dict[str, np.ndarray] = {}
    for lv in LEVELS:
        z_lv = elev.get(lv)
        f = snowlevel.snow_fraction(z_lv, sl)
        s = slr_mod.slr_at(z if has_profile else None, t if has_profile else None, z_lv, temp[lv],
                           wind_kmh=w_summit * WIND_EXPOSURE[lv])
        frac[lv] = f
        slr[lv] = s
        snow[lv] = slr_mod.snowfall_cm(precip, f, s)
        rain[lv] = precip * (1.0 - f)

    return Derived(
        model=md.model, time=md.time, grid_elevation=z_grid, has_profile=has_profile,
        precip=precip, snow_level=sl, freezing_level=fzl, lapse=used_lapse,
        wind_summit=w_summit, gust_summit=gust_summit,
        cloud=md.get("cloud_cover"), visibility=md.get("visibility"),
        temp=temp, snow=snow, rain=rain, frac_snow=frac, slr=slr,
    )


def make_donor(derived: list[Derived]) -> Optional[Donor]:
    """Median lapse rate / snow level / freezing level across models with a profile."""
    src = [d for d in derived if d.has_profile]
    if not src:
        return None
    ref = max((d.time for d in src), key=lambda t: t.shape[0])

    def med(get) -> np.ndarray:
        rows = []
        for d in src:
            a = np.full(ref.shape, np.nan)
            pos = np.searchsorted(d.time, ref)
            ok = pos < d.time.shape[0]
            ok[ok] &= d.time[pos[ok]] == ref[ok]
            # only hours this model really covers count towards the consensus
            vals = np.where(np.isfinite(d.precip), get(d), np.nan)
            a[ok] = vals[pos[ok]]
            rows.append(a)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.nanmedian(np.stack(rows), axis=0)

    lapse = med(lambda d: d.lapse)
    return Donor(time=ref, lapse=np.where(np.isfinite(lapse), lapse, lapse_mod.DEFAULT_LAPSE),
                 snow_level=med(lambda d: d.snow_level), freezing_level=med(lambda d: d.freezing_level))
