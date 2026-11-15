import numpy as np
import pytest

from pipeline.process.blend import (blend, daily_range, ensemble_agreement, ensemble_confidence,
                                    model_spread_confidence, weighted_quantile, weights_for)


def test_weights_change_with_lead_time():
    ids = ["ncep_hrrr_conus", "ecmwf_ifs", "gfs_global"]
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


def test_ensemble_agreement_is_the_share_of_members_near_the_point():
    w = [1.0] * 10
    members = [0, 2, 8, 9, 10, 11, 12, 14, 30, 40]
    # point 10 cm: "near" is 5..15 cm -> 6 of 10 members
    assert ensemble_agreement(10.0, members, w) == pytest.approx(0.6)
    # dry forecast: members under 5 cm agree -> 2 of 10
    assert ensemble_agreement(0.0, members, w) == pytest.approx(0.2)
    # big storm: +-50 % of 30 cm is 15..45 -> 2 of 10
    assert ensemble_agreement(30.0, members, w) == pytest.approx(0.2)
    # weights count, missing members do not vote
    assert ensemble_agreement(10.0, [10.0, 40.0, float("nan")], [3.0, 1.0, 5.0]) == pytest.approx(0.75)
    assert np.isnan(ensemble_agreement(10.0, [], []))
    assert np.isnan(ensemble_agreement(float("nan"), members, w))


def test_ensemble_confidence_levels_and_lead_cap():
    assert ensemble_confidence(0.8, 2) == "high"
    assert ensemble_confidence(0.5, 2) == "high"
    assert ensemble_confidence(0.3, 2) == "medium"
    assert ensemble_confidence(0.1, 2) == "low"
    assert ensemble_confidence(0.9, 7) == "medium"      # a week out is never "high"
    assert ensemble_confidence(0.1, 9) == "low"
    assert ensemble_confidence(float("nan"), 1) == "low"


def test_model_spread_confidence_is_the_fallback():
    w = [1.0] * 4
    assert model_spread_confidence([20.0, 22.0, 19.0, 21.0], w, 1) == "high"
    assert model_spread_confidence([0.0, 0.0, 0.5, 0.0], w, 1) == "high"        # agreeing on a dry day
    assert model_spread_confidence([2.0, 40.0, 10.0, 25.0], w, 1) == "low"
    assert model_spread_confidence([20.0, 22.0, 19.0, 21.0], w, 7) == "medium"  # capped by lead time
    assert model_spread_confidence([20.0], [1.0], 1) == "medium"


def test_daily_range_prefers_the_ensemble_and_always_contains_the_point():
    nan = float("nan")
    assert daily_range(10.0, 4.0, 18.0, [1.0, 2.0], [1.0, 1.0]) == (4.0, 18.0, "ensemble")
    assert daily_range(10.0, 12.0, 18.0, [], []) == (10.0, 18.0, "ensemble")     # widened down to the point
    assert daily_range(25.0, 4.0, 18.0, [], []) == (4.0, 25.0, "ensemble")       # widened up to the point
    lo, hi, src = daily_range(10.0, nan, nan, [5.0, 20.0], [1.0, 1.0])
    assert src == "models" and lo <= 10.0 <= hi
    assert daily_range(3.0, nan, nan, [], []) == (3.0, 3.0, "models")
