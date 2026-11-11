"""Model catalogue and blend weights.

Model identifiers were verified against the live Open-Meteo API (2026-11).
A model that returns no data is dropped from the blend and flagged in the
published manifest, so this list can stay generous.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .resorts import Resort

SCHEMA_VERSION = 1
FORECAST_DAYS = 16
PAST_DAYS = 1
HOURLY_HORIZON_H = 168
PRESSURE_LEVELS = (925, 850, 700, 600, 500)  # hPa, lowest first

# A ski day D runs 16:00 (D-1) -> 16:00 D local time.
NIGHT_START_H = 16  # lifts close
DAY_START_H = 8     # lifts open

SOURCES = [
    {"name": "Open-Meteo", "url": "https://open-meteo.com/", "license": "CC BY 4.0"},
    {"name": "ECMWF open data", "url": "https://www.ecmwf.int/en/forecasts/datasets/open-data", "license": "CC BY 4.0"},
    {"name": "NOAA/NCEP (GFS, NBM, HRRR, RRFS)", "url": "https://www.noaa.gov/", "license": "public domain"},
    {"name": "DWD ICON", "url": "https://www.dwd.de/", "license": "CC BY 4.0"},
    {"name": "Environment and Climate Change Canada (GEM, HRDPS)", "url": "https://eccc-msc.github.io/open-data/", "license": "ECCC open licence"},
    {"name": "JMA", "url": "https://www.jma.go.jp/", "license": "JMA terms"},
]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    kind: str                       # global | regional | blend | ai
    countries: Optional[tuple[str, ...]] = None  # None = everywhere
    exclude_states: tuple[str, ...] = ()


CONUS_EXCLUDE = ("AK", "HI")

MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("ecmwf_ifs025", "ECMWF IFS", "global"),
    ModelSpec("ecmwf_aifs025_single", "ECMWF AIFS", "ai"),
    ModelSpec("gfs_global", "GFS", "global"),
    ModelSpec("icon_seamless", "ICON", "global"),
    ModelSpec("gem_global", "GEM", "global"),
    ModelSpec("ncep_nbm_conus", "NBM", "blend", ("US",), CONUS_EXCLUDE),
    ModelSpec("ncep_hrrr_conus", "HRRR", "regional", ("US",), CONUS_EXCLUDE),
    ModelSpec("ncep_rrfs_conus", "RRFS", "regional", ("US",), CONUS_EXCLUDE),
    ModelSpec("gem_hrdps_continental", "HRDPS", "regional", ("CA",)),
    ModelSpec("jma_seamless", "JMA", "regional", ("JP",)),
)
MODEL_BY_ID = {m.id: m for m in MODELS}


def models_for(resort: Resort) -> list[ModelSpec]:
    out = []
    for m in MODELS:
        if m.countries is not None and resort.country not in m.countries:
            continue
        if resort.state in m.exclude_states:
            continue
        out.append(m)
    return out


# Phase-1 blend weights by lead time (hours). Empirical starting values:
# high-resolution models dominate the first two days, ECMWF/NBM the medium
# range. Phase 4 replaces these with verification-driven per-resort weights.
# Each row: (lead_hours_upper_bound_exclusive, {model_id: weight}).
BLEND_WEIGHTS: tuple[tuple[float, dict[str, float]], ...] = (
    (48, {
        "ncep_hrrr_conus": 3.0, "ncep_rrfs_conus": 2.5, "gem_hrdps_continental": 3.0,
        "jma_seamless": 3.0, "ncep_nbm_conus": 3.0, "ecmwf_ifs025": 2.0,
        "gfs_global": 1.5, "icon_seamless": 1.5, "gem_global": 1.0, "ecmwf_aifs025_single": 1.0,
    }),
    (120, {
        "ncep_nbm_conus": 3.0, "ecmwf_ifs025": 3.0, "gfs_global": 2.0, "jma_seamless": 2.0,
        "icon_seamless": 1.5, "ecmwf_aifs025_single": 1.5, "ncep_rrfs_conus": 1.0,
        "gem_hrdps_continental": 1.0, "gem_global": 1.0,
    }),
    (float("inf"), {
        "ecmwf_ifs025": 3.0, "ncep_nbm_conus": 2.5, "gfs_global": 2.0,
        "ecmwf_aifs025_single": 2.0, "icon_seamless": 1.0, "gem_global": 1.0, "jma_seamless": 1.0,
    }),
)
