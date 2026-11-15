"""Powder score and planner.json (design doc B1, revised by the planner backtest)."""
import json

import pytest

from pipeline.process.derive import derive
from pipeline.publish import planner as P
from pipeline.publish.build import build_resort
from tests.helpers import make_resort
from tests.test_derive_build import NOW, _ens_raw, _mds


def test_powder_score_hand_examples():
    assert P.raw_score(10, "powder", 0.0, False, 50) == pytest.approx(44.0)          # 10 cm light snow, calm
    assert P.raw_score(10, "packed", None, False, None) == pytest.approx(40.0)
    assert P.raw_score(30, "packed", 0.0, False, 0) == pytest.approx(120.0)           # not capped at 100
    assert P.raw_score(10, "heavy", 5.0, False, 80) == pytest.approx(40 * 0.8 * 0.8 * 0.8)
    assert P.raw_score(10, "packed", 5.0, True, 0) == pytest.approx(20.0)            # rain at mid replaces the base penalty
    assert P.raw_score(10, "packed", 0.0, False, 120) == pytest.approx(20.0)         # lifts likely on wind hold
    assert P.raw_score(0, "powder", 0.0, False, 0) == 0.0


def test_ensemble_ratio():
    assert P.ensemble_ratio(10, 5, 10, 14) == pytest.approx((0.3 * 5 + 0.4 * 10 + 0.3 * 14) / 10)
    assert P.ensemble_ratio(10, 0, 0, 0) == 0.25                                     # bounded
    assert P.ensemble_ratio(10, 20, 40, 80) == 1.1                                   # upside counts little
    assert P.ensemble_ratio(None, 1, 2, 3) == 1.0 and P.ensemble_ratio(0.5, 1, 2, 3) == 1.0
    assert P.ensemble_ratio(10, None, 2, 3) == 1.0


def test_rain_at_mid():
    day = {"snow_level_m": {"min": 1800, "max": 2500, "during_precip": True}, "precip_mm": 10.0}
    assert P.rain_at_mid(day, 2300)
    assert not P.rain_at_mid(day, 2600)
    assert not P.rain_at_mid({**day, "precip_mm": 0.5}, 2300)                       # a few drops do not count
    assert not P.rain_at_mid({**day, "snow_level_m": {**day["snow_level_m"], "during_precip": False}}, 2300)


def _doc():
    r = make_resort()
    return build_resort(r, [derive(m, r) for m in _mds()], NOW, ens_raw=_ens_raw(), tier="featured")


def test_planner_days_from_a_document():
    doc = _doc()
    points, probs = P.planner_days(doc)
    assert len(points) == 10 and len(probs) == 6
    row = dict(zip(P.POINT_FIELDS, points[2]))
    d1, d2 = doc["daily"][1], doc["daily"][2]
    assert row["date"] == d2["date"] and row["lead"] == 2 and row["cm"] == d2["snow_cm"]["mid"]
    assert row["night"] == pytest.approx(d2["snow_night_cm"]["mid"], abs=0.05)
    # fresh snow at opening = overnight + half of yesterday's lift-hours snow
    assert row["fresh"] == pytest.approx(d2["snow_night_cm"]["mid"] + 0.5 * d1["snow_day_cm"]["mid"], abs=0.06)
    first = dict(zip(P.POINT_FIELDS, points[0]))
    assert first["fresh"] == pytest.approx(first["night"], abs=0.06)                  # no yesterday in the document
    assert row["p15"] == d2["ens"]["prob"]["15"]["mid"] and row["conf"] == d2["confidence"]
    assert row["score"] >= 0 and row["rain_mid"] in (0, 1)
    prob = dict(zip(P.PROB_FIELDS, probs[0]))
    assert prob["lead"] == 10 and prob["p15"] == doc["daily_prob"][0]["ens"]["prob"]["15"]["mid"]


def test_build_planner_shape():
    doc = _doc()
    out = P.build_planner([{"id": "tahoe", "name": "Tahoe", "name_zh": "太浩湖"}], [doc], NOW)
    json.dumps(out, allow_nan=False)
    assert out["fields"] == list(P.POINT_FIELDS) and out["prob_fields"] == list(P.PROB_FIELDS)
    r = out["resorts"]["test-mountain"]
    assert r["passes"] == {"ikon": "unlimited"} and r["mid_m"] == 2300 and r["timezone"] == "America/Los_Angeles"
    assert len(r["days"]) == 10 and len(r["prob_days"]) == 6 and r["generated_at"] == doc["generated_at"]
    assert out["regions"][0]["id"] == "tahoe"
