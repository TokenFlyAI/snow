import numpy as np
import pytest

from pipeline.process import slr
from tests.helpers import std_profile


def test_kuchera_reference_values():
    assert slr.kuchera_slr(271.16) == pytest.approx(12.0)
    assert slr.kuchera_slr(273.15) == pytest.approx(8.02)        # 0 degC: heavy, wet snow
    assert slr.kuchera_slr(263.15) == pytest.approx(20.01)       # -10 degC: dry powder
    assert slr.kuchera_slr(274.15) == pytest.approx(6.02)


def test_kuchera_is_clamped_and_nan_safe():
    assert slr.kuchera_slr(280.0) == slr.SLR_MIN
    assert slr.kuchera_slr(230.0) == slr.SLR_MAX
    assert np.isnan(slr.kuchera_slr(np.nan))


def test_ratio_is_not_a_fixed_ten_to_one():
    cold, warm = slr.kuchera_slr(np.array([258.15, 272.65]))
    assert 15.0 <= cold <= 25.0 and 5.0 <= warm <= 10.0


def test_column_tmax_ignores_levels_below_ground_and_finds_warm_nose():
    z, t = std_profile(1, t_sea_level=5.0)        # warm underground levels
    assert slr.column_tmax_c(z, t, 2500.0, np.array([-11.0]))[0] == pytest.approx(-11.0)
    t2 = t.copy()
    t2[2, 0] = -1.0                               # warm layer at 3010 m above a cold surface
    assert slr.column_tmax_c(z, t2, 2500.0, np.array([-11.0]))[0] == pytest.approx(-1.0)


def test_wind_compaction_factor():
    f = slr.wind_factor(np.array([0.0, 25.0, 57.5, 90.0, 200.0, np.nan]))
    assert f == pytest.approx([1.0, 1.0, 0.825, 0.65, 0.65, 1.0])
    calm = slr.slr_at(None, None, 2500.0, np.array([-10.0]), wind_kmh=np.array([10.0]))[0]
    gale = slr.slr_at(None, None, 2500.0, np.array([-10.0]), wind_kmh=np.array([120.0]))[0]
    assert gale == pytest.approx(calm * 0.65)


def test_snowfall_amount():
    assert slr.snowfall_cm(10.0, 1.0, 10.0) == pytest.approx(10.0)    # 10 mm at 10:1 -> 10 cm
    assert slr.snowfall_cm(10.0, 1.0, 18.0) == pytest.approx(18.0)
    assert slr.snowfall_cm(10.0, 0.0, 12.0) == 0.0                    # all rain
    mixed = slr.snowfall_cm(10.0, 0.5, 10.0)
    assert 0.0 < mixed < 5.0                                           # melting layer packs denser


def test_quality_labels():
    assert slr.snow_quality(17.0) == "powder"
    assert slr.snow_quality(11.0) == "packed"
    assert slr.snow_quality(6.0) == "heavy"
    assert slr.snow_quality(float("nan")) == "none"
