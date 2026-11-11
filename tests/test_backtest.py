"""Backtest on a real storm: the Sierra Nevada blizzard of 28 Feb - 5 Mar 2024.

Fixture (scripts/make_backtest_fixture.py): archived GFS / ECMWF / HRRR
forecasts from the Open-Meteo Historical Forecast API at SNOTEL 784
"Palisades Tahoe" (2441 m), plus the station's own daily observations.

What the station can and cannot verify:
- the precipitation gauge (PREC) gives the liquid total: 208 mm. Gauges
  under-catch in blizzard winds, so models above it are expected.
- the snow-depth sensor is unreliable in this storm (depth *fell* 23 cm on
  2 Mar while it was still snowing hard), so it only gives a lower bound on
  new snow, not a check of the snow-to-liquid ratio. That needs resort snow
  reports, which phase 4 adds.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.ingest.open_meteo import parse_location
from pipeline.process import slr as slr_mod
from pipeline.process.derive import derive
from pipeline.resorts import Resort

FIXTURE = Path(__file__).parent / "fixtures" / "palisades_2024_03_blizzard.json"
IN_TO_MM = 25.4


@pytest.fixture(scope="module")
def case():
    fx = json.loads(FIXTURE.read_text())
    st = fx["station"]
    resort = Resort(id="snotel-784", name=st["name"], country="US", state="CA", region="tahoe",
                    lat=st["lat"], lon=st["lon"], timezone="America/Los_Angeles",
                    elevation_m={"base": 1890, "mid": st["elevation_m"], "summit": 2758})
    derived = {m: derive(parse_location(p, m, resort.id), resort) for m, p in fx["models"].items()}
    return fx, resort, derived


def _obs_liquid_mm(fx) -> float:
    prec = fx["observed"]["PREC"]["values"]
    return (prec["2024-03-05"] - prec["2024-02-28"]) * IN_TO_MM


def test_observed_storm_total(case):
    fx, _, _ = case
    assert _obs_liquid_mm(fx) == pytest.approx(208.3, abs=0.5)


def test_model_liquid_brackets_the_gauge(case):
    fx, _, derived = case
    obs = _obs_liquid_mm(fx)
    ratios = {m: float(np.nansum(d.precip)) / obs for m, d in derived.items()}
    # ECMWF ~1.0x, HRRR ~1.3x, GFS ~1.5x the (under-catching) gauge
    assert all(0.85 <= r <= 1.65 for r in ratios.values()), ratios
    assert ratios["ecmwf_ifs025"] < ratios["ncep_hrrr_conus"] < ratios["gfs_global"]
    assert 1.0 <= float(np.mean(list(ratios.values()))) <= 1.45


def test_station_stays_all_snow_and_base_sees_some_rain_risk(case):
    _, resort, derived = case
    for m, d in derived.items():
        wet = d.precip > 0.2
        assert d.frac_snow["mid"][wet].min() == 1.0, m             # 2441 m: snow for the whole storm
        assert d.snow_level[wet].max() < resort.elevation_m.mid, m
        assert d.temp["summit"][wet].mean() < d.temp["mid"][wet].mean() < d.temp["base"][wet].mean()


def test_grid_height_differences_are_removed_by_the_correction(case):
    _, _, derived = case
    grid = [d.grid_elevation for d in derived.values()]
    assert max(grid) - min(grid) > 200                              # 2070 m ... 2291 m
    t_mid = [float(np.nanmean(d.temp["mid"])) for d in derived.values()]
    assert max(t_mid) - min(t_mid) < 1.5


def test_snow_ratio_is_cold_storm_but_wind_packed(case):
    _, _, derived = case
    for m, d in derived.items():
        wet = d.precip > 0.2
        mean_slr = float(np.nansum(d.slr["mid"][wet] * d.precip[wet]) / np.nansum(d.precip[wet]))
        # ECMWF's archived pressure-level winds are weak here, so it keeps ~17:1
        assert 9.0 <= mean_slr <= 18.0, (m, mean_slr)
        assert mean_slr > 10.0 or d.wind_summit[wet].mean() > 60     # low ratios only come from wind
    # the same storm with calm air would be far fluffier: the wind factor matters here
    gfs = derived["gfs_global"]
    wet = gfs.precip > 0.2
    assert slr_mod.wind_factor(gfs.wind_summit[wet] * 0.75).mean() < 0.9


def test_new_snow_exceeds_the_measured_depth_gain(case):
    fx, _, derived = case
    depth = fx["observed"]["SNWD"]["values"]
    gain_cm = (depth["2024-03-01"] - depth["2024-02-29"]) * 2.54     # +69 cm in one day
    assert gain_cm == pytest.approx(68.6, abs=0.5)
    for m, d in derived.items():
        t = d.time
        day = (t > np.datetime64("2024-02-29T08")) & (t <= np.datetime64("2024-03-01T08"))
        assert float(np.nansum(d.snow["mid"][day])) > 0.6 * gain_cm, m   # settling: new snow >= depth gain
        total = float(np.nansum(d.snow["mid"]))
        assert 180 <= total <= 420, (m, total)                            # 1.8 - 4.2 m, not 5+ m
