import numpy as np
import pytest

from pipeline.process.thermo import pressure_at, sat_vapor_pressure, wet_bulb, wind_chill


def test_saturation_vapour_pressure_reference_points():
    assert sat_vapor_pressure(0.0) == pytest.approx(6.112, abs=0.01)
    assert sat_vapor_pressure(20.0) == pytest.approx(23.4, abs=0.2)


def test_wet_bulb_equals_temperature_when_saturated():
    assert wet_bulb(5.0, 100.0, 850.0) == pytest.approx(5.0, abs=0.02)


def test_wet_bulb_reference_value_at_sea_level():
    # 20 degC / 50 % RH at 1013 hPa -> ~13.8 degC on a psychrometric chart
    assert wet_bulb(20.0, 50.0, 1013.25) == pytest.approx(13.8, abs=0.3)


def test_wet_bulb_drops_in_dry_air_and_handles_nan():
    tw = wet_bulb(np.array([2.0, 2.0, np.nan]), np.array([90.0, 30.0, 50.0]), 750.0)
    assert tw[1] < tw[0] < 2.0
    assert tw[1] < 0.0  # +2 degC air at 30 % RH still supports snow
    assert np.isnan(tw[2])


def test_standard_pressure():
    assert pressure_at(0.0) == pytest.approx(1013.25)
    assert pressure_at(3000.0) == pytest.approx(701, abs=3)


def test_wind_chill_reference_and_bounds():
    # Environment Canada table: -10 degC at 30 km/h feels like about -20
    assert wind_chill(-10.0, 30.0) == pytest.approx(-19.5, abs=0.6)
    assert wind_chill(-10.0, 2.0) == -10.0     # calm: no chill
    assert wind_chill(15.0, 40.0) == 15.0      # warm: formula not applied
