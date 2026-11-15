"""Model catalogue, ensemble catalogue, refresh tiers and blend weights.

Model identifiers were verified against the live Open-Meteo API (2026-11).
A model that returns no data is dropped from the blend and flagged in the
published manifest, so this list can stay generous.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

from .resorts import Resort

SCHEMA_VERSION = 2
# Deterministic models are only used for point values, i.e. ski days D+0 .. D+9.
# 12 forecast days + 1 past day = 13 days, which stays inside one "14-day" unit
# of the Open-Meteo call accounting.
FORECAST_DAYS = 12
PAST_DAYS = 1
POINT_DAYS = 10          # daily entries with a point value: lead_days 0..9
DAILY_DAYS = 16          # daily entries in total; lead_days 10..15 are probabilities only
OUTLOOK_WEEKS = (3, 4, 5)  # week n covers lead days 7(n-1) .. 7n-1
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
    {"name": "Météo-France (AROME, ARPEGE)", "url": "https://meteofrance.com/", "license": "Etalab open licence"},
    {"name": "MeteoSwiss (ICON-CH1/CH2)", "url": "https://www.meteoswiss.admin.ch/", "license": "CC BY 4.0"},
    {"name": "UK Met Office (global 10 km)", "url": "https://www.metoffice.gov.uk/", "license": "CC BY-SA 4.0"},
    {"name": "CMA (GRAPES global)", "url": "https://www.cma.gov.cn/", "license": "CMA terms"},
    {"name": "Ensembles: ECMWF ENS, NOAA GEFS, ECCC GEPS, DWD ICON-EPS", "url": "https://open-meteo.com/en/docs/ensemble-api", "license": "CC BY 4.0"},
    {"name": "OpenStreetMap contributors (resort positions, base map via OpenFreeMap)", "url": "https://www.openstreetmap.org/copyright", "license": "ODbL"},
]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    kind: str                       # global | regional | blend | ai
    countries: Optional[tuple[str, ...]] = None  # None = everywhere
    exclude_states: tuple[str, ...] = ()


CONUS_EXCLUDE = ("AK", "HI")
ALPS = ("FR", "CH", "IT", "AT")
NOT_NORTH_AMERICA = ("FR", "CH", "IT", "AT", "AD", "JP", "KR", "CN", "AU", "NZ", "CL")

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
    # JMA: MSM 5 km over Japan, the global GSM elsewhere in East Asia
    ModelSpec("jma_seamless", "JMA", "regional", ("JP", "KR", "CN")),
    # Europe (phase 2). icon_seamless above already nests ICON-D2 (2 km) and ICON-EU (7 km) over the Alps.
    # At most 8 models per resort: the model chart has 8 fixed colour slots.
    ModelSpec("meteofrance_seamless", "Météo-France", "regional", ("FR", "CH", "IT", "AT", "AD")),  # AROME 1.3 km / ARPEGE
    ModelSpec("meteoswiss_icon_seamless", "MeteoSwiss", "regional", ALPS),                          # ICON-CH1/CH2, Alpine arc
    # Rest of the world outside North America: a third global model at 10 km
    ModelSpec("ukmo_seamless", "UKMO", "global", NOT_NORTH_AMERICA),
    ModelSpec("cma_grapes_global", "CMA", "global", ("CN",)),
)
MODEL_BY_ID = {m.id: m for m in MODELS}

TIERS = ("featured", "standard")


def _applies(m: ModelSpec, resort: Resort) -> bool:
    if m.countries is not None and resort.country not in m.countries:
        return False
    return resort.state not in m.exclude_states


def _regional_pick(resort: Resort) -> str:
    """The one extra model a standard-tier resort gets on top of ECMWF IFS and GFS."""
    c = resort.country
    if c == "US":
        return "ncep_nbm_conus" if resort.state not in CONUS_EXCLUDE else "icon_seamless"
    if c == "CA":
        return "gem_hrdps_continental"
    if c in ("JP", "KR", "CN"):
        return "jma_seamless"
    if c in ("FR", "CH", "IT", "AT", "AD"):
        return "icon_seamless"       # ICON-D2 + ICON-EU nest
    return "ukmo_seamless"


def models_for(resort: Resort, tier: str = "featured") -> list[ModelSpec]:
    """Deterministic models fetched for a resort.

    featured: every model that covers the resort.
    standard: ECMWF IFS + GFS + the best regional model (3 models), to stay inside the API budget.
    """
    full = [m for m in MODELS if _applies(m, resort)]
    if tier == "featured":
        return full
    keep = {"ecmwf_ifs025", "gfs_global", _regional_pick(resort)}
    return [m for m in full if m.id in keep]


# --------------------------------------------------------------------------- ensembles
@dataclass(frozen=True)
class EnsembleSpec:
    id: str
    label: str
    members: int          # including the control run
    days: int             # forecast_days requested
    weight: float         # weight of the whole model in the pooled distribution
    tiers: tuple[str, ...] = TIERS


# Verified on the Open-Meteo Ensemble API (2026-11): member fields are `snowfall_member01` ...
ENSEMBLES: tuple[EnsembleSpec, ...] = (
    EnsembleSpec("ecmwf_ifs025", "ECMWF ENS", 51, 15, 2.0, ("featured",)),
    EnsembleSpec("gfs05", "GEFS", 31, 35, 1.0),
    EnsembleSpec("gem_global", "GEPS", 21, 35, 1.0, ("featured",)),
    EnsembleSpec("icon_seamless", "ICON-EPS", 40, 8, 1.0, ("featured",)),
)
ENSEMBLE_BY_ID = {e.id: e for e in ENSEMBLES}


def ensembles_for(tier: str) -> list[EnsembleSpec]:
    return [e for e in ENSEMBLES if tier in e.tiers]


# --------------------------------------------------------------------------- refresh tiers and API budget
FEATURED_PATH = Path(__file__).resolve().parent.parent / "data" / "featured.yaml"
RUNS_PER_DAY = 4
REFRESH_SLOTS_UTC = (2, 8, 14, 20)       # the forecast workflow's cron hours
API_DAILY_LIMIT = 10_000                 # Open-Meteo free tier, weighted calls per day
API_DAILY_TARGET = 8_000                 # what we allow ourselves
API_PER_MINUTE = 480                     # free tier allows 600 per minute
API_PER_HOUR = 4_800                     # ... and 5,000 per hour (a full run is ~4,500)
STALE_AFTER_H = 28.0                     # a once-a-day product older than this is refreshed out of turn
# ... and one younger than this is not refreshed again in its slot. A regular daily refresh is
# ~24 h old when its slot comes round; 18 h keeps a full run (first deploy, lost previous data)
# from being followed by a second round of regional refreshes on the same day.
FRESH_WITHIN_H = 18.0


def load_featured(path: Path | str = FEATURED_PATH) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    return list(doc.get("featured") or [])


def refresh_slot(lon: float) -> int:
    """UTC hour of the run that refreshes a resort's once-a-day products.

    Chosen so the refresh lands before the local morning: Europe 02:37 UTC,
    eastern North America 08:37, western North America 14:37 (06:37 PST, with
    the 06Z cycle), Asia / Oceania 20:37 (05:37 JST).
    """
    if -30.0 <= lon < 60.0:
        return 2
    if -100.0 <= lon < -30.0:
        return 8
    if lon < -100.0:
        return 14
    return 20


def current_slot(utc_hour: int) -> int:
    """The refresh slot a run started at `utc_hour` belongs to (cron delays included)."""
    return REFRESH_SLOTS_UTC[((utc_hour - 2) % 24) // 6]


def call_weight(n_vars: float, n_days: int, n_locations: int = 1) -> float:
    """Open-Meteo free-tier accounting: 10 variables and 14 days each count as one call.
    For ensembles every member of every variable counts as a variable."""
    return max(1.0, n_vars / 10.0) * max(1.0, n_days / 14.0) * n_locations


def estimate_daily_calls(resorts: Iterable[Resort], featured: Iterable[str], n_hourly_vars: int) -> dict:
    """Weighted Open-Meteo calls per day for the scheduled runs (4 a day)."""
    fset = set(featured)
    det_w = call_weight(n_hourly_vars, FORECAST_DAYS + PAST_DAYS)
    out = {"featured_deterministic": 0.0, "standard_deterministic": 0.0, "ensembles": 0.0}
    for r in resorts:
        tier = "featured" if r.id in fset else "standard"
        n = len(models_for(r, tier))
        if tier == "featured":
            out["featured_deterministic"] += n * det_w * RUNS_PER_DAY
        else:
            out["standard_deterministic"] += n * det_w
        out["ensembles"] += sum(call_weight(e.members, e.days) for e in ensembles_for(tier))
    out["total"] = sum(out.values())
    return {k: round(v, 1) for k, v in out.items()}


# Phase-1 blend weights by lead time (hours). Empirical starting values:
# high-resolution models dominate the first two days, ECMWF/NBM the medium
# range. Phase 4 replaces these with verification-driven per-resort weights.
# Each row: (lead_hours_upper_bound_exclusive, {model_id: weight}).
BLEND_WEIGHTS: tuple[tuple[float, dict[str, float]], ...] = (
    (48, {
        "ncep_hrrr_conus": 3.0, "ncep_rrfs_conus": 2.5, "gem_hrdps_continental": 3.0,
        "jma_seamless": 3.0, "ncep_nbm_conus": 3.0, "ecmwf_ifs025": 2.0,
        "gfs_global": 1.5, "icon_seamless": 1.5, "gem_global": 1.0, "ecmwf_aifs025_single": 1.0,
        "meteofrance_seamless": 3.0, "meteoswiss_icon_seamless": 3.0,
        "ukmo_seamless": 1.5, "cma_grapes_global": 0.5,
    }),
    (120, {
        "ncep_nbm_conus": 3.0, "ecmwf_ifs025": 3.0, "gfs_global": 2.0, "jma_seamless": 2.0,
        "icon_seamless": 1.5, "ecmwf_aifs025_single": 1.5, "ncep_rrfs_conus": 1.0,
        "gem_hrdps_continental": 1.0, "gem_global": 1.0,
        "meteofrance_seamless": 2.0, "meteoswiss_icon_seamless": 2.0,
        "ukmo_seamless": 2.0, "cma_grapes_global": 0.5,
    }),
    (float("inf"), {
        "ecmwf_ifs025": 3.0, "ncep_nbm_conus": 2.5, "gfs_global": 2.0,
        "ecmwf_aifs025_single": 2.0, "icon_seamless": 1.0, "gem_global": 1.0, "jma_seamless": 1.0,
        "ukmo_seamless": 1.5, "meteofrance_seamless": 0.5, "meteoswiss_icon_seamless": 0.5, "cma_grapes_global": 0.5,
    }),
)
