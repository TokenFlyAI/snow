"""Synthetic data builders shared by the tests."""
from __future__ import annotations

import numpy as np

from pipeline.config import PRESSURE_LEVELS
from pipeline.ingest.open_meteo import ModelData
from pipeline.resorts import Resort

LEVEL_Z = {925: 760.0, 850: 1460.0, 700: 3010.0, 600: 4200.0, 500: 5570.0}


def make_resort(**kw) -> Resort:
    base = dict(id="test-mountain", name="Test Mountain", country="US", state="CA", region="tahoe",
                lat=39.2, lon=-120.25, elevation_m={"base": 1900, "mid": 2300, "summit": 2750},
                timezone="America/Los_Angeles", passes={"ikon": "unlimited"})
    base.update(kw)
    return Resort(**base)


def std_profile(n: int, t_sea_level: float = 15.0, lapse_c_per_km: float = 6.5):
    """(z, t) arrays of shape (n_levels, n) for a constant-lapse atmosphere."""
    z = np.array([[LEVEL_Z[p]] * n for p in PRESSURE_LEVELS], dtype=float)
    t = t_sea_level - lapse_c_per_km * z / 1000.0
    return z, t


def make_model_data(model: str = "gfs_global", n: int = 96, start: str = "2026-01-10T00",
                    grid_elevation: float = 2100.0, t_sea_level: float = 10.0, lapse: float = 6.5,
                    rh: float = 95.0, precip_mm_per_h: float = 0.0, wind_kmh: float = 20.0,
                    with_profile: bool = True, valid_hours: int | None = None) -> ModelData:
    time = np.datetime64(start, "h") + np.arange(n).astype("timedelta64[h]")
    md = ModelData(model=model, resort_id="test-mountain", grid_elevation=grid_elevation, time=time)
    t2m = np.full(n, t_sea_level - lapse * grid_elevation / 1000.0)
    md.v["temperature_2m"] = t2m
    md.v["relative_humidity_2m"] = np.full(n, rh)
    md.v["precipitation"] = np.full(n, precip_mm_per_h)
    md.v["snowfall"] = np.zeros(n)
    md.v["wind_speed_10m"] = np.full(n, wind_kmh * 0.5)
    md.v["wind_gusts_10m"] = np.full(n, wind_kmh)
    md.v["cloud_cover"] = np.full(n, 80.0)
    md.v["visibility"] = np.full(n, 10000.0)
    md.v["freezing_level_height"] = np.full(n, np.nan)
    if with_profile:
        z, t = std_profile(n, t_sea_level, lapse)
        for i, p in enumerate(PRESSURE_LEVELS):
            md.v[f"geopotential_height_{p}hPa"] = z[i]
            md.v[f"temperature_{p}hPa"] = t[i]
            md.v[f"relative_humidity_{p}hPa"] = np.full(n, rh)
            md.v[f"wind_speed_{p}hPa"] = np.full(n, wind_kmh)
    if valid_hours is not None:
        for k in md.v:
            md.v[k] = md.v[k].copy()
            md.v[k][valid_hours:] = np.nan
    return md
