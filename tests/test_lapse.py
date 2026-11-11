import numpy as np
import pytest

from pipeline.process.lapse import DEFAULT_LAPSE, MAX_LAPSE, MIN_LAPSE, correct_temperature, layer_lapse
from tests.helpers import std_profile


def test_lapse_recovered_from_profile():
    z, t = std_profile(4, lapse_c_per_km=5.0)
    assert layer_lapse(z, t, 2000.0, 2800.0) == pytest.approx([5.0] * 4)


def test_correction_cools_going_up_and_warms_going_down():
    z, t = std_profile(1, lapse_c_per_km=6.5)
    up, g = correct_temperature(np.array([0.0]), 2000.0, 2700.0, z, t)
    down, _ = correct_temperature(np.array([0.0]), 2000.0, 1500.0, z, t)
    assert g[0] == pytest.approx(6.5)
    assert up[0] == pytest.approx(-4.55)
    assert down[0] == pytest.approx(3.25)


def test_inversion_is_clamped_to_minimum_lapse():
    z, _ = std_profile(1)
    t = np.array([[-8.0], [-6.0], [-2.0], [-10.0], [-20.0]])   # warming with height up to 700 hPa
    assert layer_lapse(z, t, 1500.0, 2900.0)[0] == MIN_LAPSE


def test_superadiabatic_layer_is_clamped_to_dry_adiabat():
    z, t = std_profile(1, lapse_c_per_km=14.0)
    assert layer_lapse(z, t, 1500.0, 2900.0)[0] == MAX_LAPSE


def test_without_profile_default_lapse_is_used():
    out, g = correct_temperature(np.array([1.0, 2.0]), 2000.0, 3000.0)
    assert g == pytest.approx([DEFAULT_LAPSE] * 2)
    assert out == pytest.approx([-5.5, -4.5])


def test_explicit_lapse_overrides_and_nan_profile_falls_back():
    out, _ = correct_temperature(np.array([0.0]), 1000.0, 2000.0, lapse=np.array([8.0]))
    assert out[0] == pytest.approx(-8.0)
    z, t = std_profile(1)
    t[:] = np.nan
    out, g = correct_temperature(np.array([0.0]), 1000.0, 2000.0, z, t)
    assert g[0] == DEFAULT_LAPSE and out[0] == pytest.approx(-6.5)


def test_thin_layer_is_padded_not_noisy():
    z, t = std_profile(1, lapse_c_per_km=6.5)
    assert layer_lapse(z, t, 2000.0, 2010.0)[0] == pytest.approx(6.5)
