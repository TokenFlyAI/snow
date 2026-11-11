import numpy as np
import pytest

from pipeline.config import PRESSURE_LEVELS
from pipeline.process import snowlevel
from tests.helpers import std_profile


def test_saturated_air_snow_level_just_below_freezing_level():
    z, t = std_profile(1, t_sea_level=13.0)            # 0 degC at 2000 m
    rh = np.full_like(t, 100.0)
    fzl = snowlevel.freezing_level(z, t)[0]
    sl = snowlevel.snow_level(z, t, rh, PRESSURE_LEVELS)[0]
    assert fzl == pytest.approx(2000.0, abs=1)
    assert sl == pytest.approx(2000.0 - 0.5 / 0.0065, abs=10)   # where Tw = +0.5 degC


def test_dry_air_lowers_the_snow_level():
    z, t = std_profile(1, t_sea_level=13.0)
    moist = snowlevel.snow_level(z, t, np.full_like(t, 100.0), PRESSURE_LEVELS)[0]
    dry = snowlevel.snow_level(z, t, np.full_like(t, 40.0), PRESSURE_LEVELS)[0]
    assert dry < moist - 300


def test_fallback_without_humidity_is_freezing_level_minus_300():
    z, t = std_profile(1, t_sea_level=13.0)
    assert snowlevel.snow_level(z, t, None, PRESSURE_LEVELS)[0] == pytest.approx(1700.0, abs=1)


def test_snow_level_never_above_freezing_level():
    z, t = std_profile(5, t_sea_level=np.array([5.0, 9.0, 13.0, 17.0, 21.0]))
    rh = np.full_like(t, 100.0)
    assert (snowlevel.snow_level(z, t, rh, PRESSURE_LEVELS) <= snowlevel.freezing_level(z, t) + 1e-6).all()


def test_same_storm_snow_at_summit_rain_at_base():
    sl = np.array([2300.0])
    assert snowlevel.snow_fraction(2750.0, sl)[0] == 1.0     # summit: all snow
    assert snowlevel.snow_fraction(2150.0, sl)[0] == pytest.approx(0.5)
    assert snowlevel.snow_fraction(1900.0, sl)[0] == 0.0     # base: all rain
    types = snowlevel.precip_type(np.array([1.0, 0.5, 0.0, np.nan]))
    assert list(types) == [snowlevel.SNOW, snowlevel.MIX, snowlevel.RAIN, -1]


def test_surface_based_estimate():
    # saturated +0.5 degC at the grid height -> snow level is the grid height
    assert snowlevel.snow_level_from_surface(0.5, 100.0, 1800.0, 815.0) == pytest.approx(1800.0, abs=5)
    assert snowlevel.snow_level_from_surface(3.0, 100.0, 1800.0, 815.0) > 2200.0
