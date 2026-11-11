import numpy as np
import pytest

from pipeline.process.profile import crossing_height, interp_at
from tests.helpers import std_profile


def test_interp_between_levels_and_extrapolation():
    z, t = std_profile(3, t_sea_level=15.0, lapse_c_per_km=6.5)
    assert interp_at(z, t, 2000.0) == pytest.approx([2.0] * 3)
    assert interp_at(z, t, 300.0) == pytest.approx([13.05] * 3)     # below the lowest level
    assert interp_at(z, t, 6000.0) == pytest.approx([-24.0] * 3)    # above the top level


def test_interp_nan_column_returns_nan():
    z, t = std_profile(2)
    t[1, 0] = np.nan
    out = interp_at(z, t, 2000.0)
    assert np.isnan(out[0]) and np.isfinite(out[1])


def test_freezing_level_simple():
    z, t = std_profile(1, t_sea_level=13.0, lapse_c_per_km=6.5)
    assert crossing_height(z, t, 0.0)[0] == pytest.approx(2000.0, abs=1)


def test_crossing_uses_highest_level_when_there_is_a_warm_nose():
    # cold at the surface, warm layer aloft (freezing-rain set-up)
    z = np.array([[800.0], [1500.0], [3000.0], [4200.0], [5500.0]])
    t = np.array([[-3.0], [2.0], [-4.0], [-12.0], [-22.0]])
    h = crossing_height(z, t, 0.0)[0]
    assert 1500.0 < h < 3000.0
    assert h == pytest.approx(2000.0, abs=1)


def test_crossing_extrapolates_below_a_fully_frozen_column():
    z, t = std_profile(1, t_sea_level=0.0, lapse_c_per_km=6.5)   # 0 degC at sea level
    assert crossing_height(z, t, 0.0)[0] == pytest.approx(0.0, abs=5)


def test_crossing_caps_at_top_level_when_everything_is_warm():
    z, t = std_profile(1, t_sea_level=45.0)
    assert crossing_height(z, t, 0.0)[0] == z[-1, 0]
