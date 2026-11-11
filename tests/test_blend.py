import numpy as np
import pytest

from pipeline.process.blend import blend, confidence, weighted_quantile, weights_for


def test_weights_change_with_lead_time():
    ids = ["ncep_hrrr_conus", "ecmwf_ifs025", "gfs_global"]
    w = weights_for(ids, np.array([6, 72, 200]))
    assert w[0, 0] > w[1, 0] > w[2, 0]      # short range: high resolution first
    assert w[0, 1] == 0 and w[1, 1] > w[2, 1]
    assert w[0, 2] == 0 and w[1, 2] > w[2, 2]


def test_blend_is_weighted_mean():
    out = blend(np.array([[10.0], [20.0]]), np.array([[3.0], [1.0]]))
    assert out[0] == pytest.approx(12.5)


def test_missing_model_is_dropped_and_weights_renormalised():
    stack = np.array([[10.0, np.nan], [20.0, 20.0], [np.nan, np.nan]])
    w = np.array([[3.0, 3.0], [1.0, 1.0], [5.0, 5.0]])
    assert blend(stack, w) == pytest.approx([12.5, 20.0])


def test_all_missing_gives_nan_and_zero_weight_falls_back_to_mean():
    assert np.isnan(blend(np.array([[np.nan], [np.nan]]), np.ones((2, 1)))[0])
    assert blend(np.array([[4.0], [8.0]]), np.zeros((2, 1)))[0] == pytest.approx(6.0)


def test_weighted_quantile():
    v, w = [0.0, 10.0, 20.0, 30.0], [1.0, 1.0, 1.0, 1.0]
    assert weighted_quantile(v, w, 0.5) == pytest.approx(15.0)
    assert weighted_quantile(v, w, 0.1) < weighted_quantile(v, w, 0.9)
    assert weighted_quantile([5.0, float("nan")], [1.0, 1.0], 0.5) == 5.0
    assert np.isnan(weighted_quantile([], [], 0.5))
    # a heavily weighted model pulls the median towards itself
    assert weighted_quantile([0.0, 30.0], [1.0, 9.0], 0.5) > 20.0


def test_confidence_from_agreement_and_lead():
    w = [1.0] * 4
    assert confidence([20.0, 22.0, 19.0, 21.0], w, 1) == "high"
    assert confidence([0.0, 0.0, 0.5, 0.0], w, 1) == "high"        # agreeing on a dry day
    assert confidence([2.0, 40.0, 10.0, 25.0], w, 1) == "low"
    assert confidence([20.0, 22.0, 19.0, 21.0], w, 7) == "medium"  # capped by lead time
    assert confidence([20.0, 22.0, 19.0, 21.0], w, 12) == "low"
