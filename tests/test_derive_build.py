import json
from datetime import datetime, timezone

import numpy as np
import pytest

from pipeline.process.derive import derive, make_donor
from pipeline.publish.build import build_index, build_manifest, build_resort
from pipeline.resorts import LEVELS, load_resorts
from tests.helpers import make_model_data, make_resort

NOW = datetime(2026, 1, 10, 6, 0, tzinfo=timezone.utc)


def test_temperature_is_corrected_from_grid_to_each_elevation():
    r = make_resort()                                  # 1900 / 2300 / 2750 m
    d = derive(make_model_data(grid_elevation=2100.0, t_sea_level=10.0), r)
    assert d.has_profile
    assert d.temp["base"][0] == pytest.approx(10.0 - 6.5 * 1.9, abs=0.05)
    assert d.temp["summit"][0] == pytest.approx(10.0 - 6.5 * 2.75, abs=0.05)
    assert d.temp["summit"][0] < d.temp["mid"][0] < d.temp["base"][0]


def test_two_models_with_different_grid_heights_agree_after_correction():
    r = make_resort()
    a = derive(make_model_data(grid_elevation=1700.0), r)
    b = derive(make_model_data(grid_elevation=2600.0), r)
    for lv in LEVELS:
        assert a.temp[lv][0] == pytest.approx(b.temp[lv][0], abs=0.05)


def test_snow_at_summit_rain_at_base_in_the_same_storm():
    r = make_resort()
    # 0 degC isotherm at ~2380 m, saturated: snow level ~2300 m
    d = derive(make_model_data(t_sea_level=15.5, rh=100.0, precip_mm_per_h=2.0), r)
    assert 2200 < d.snow_level[0] < 2380 <= d.freezing_level[0] + 5
    assert d.frac_snow["summit"][0] == 1.0 and d.frac_snow["base"][0] == 0.0
    assert d.snow["summit"][0] > d.snow["mid"][0] > d.snow["base"][0] == 0.0
    assert d.rain["base"][0] == pytest.approx(2.0) and d.rain["summit"][0] == 0.0


def test_cold_storm_gives_fluffier_snow_than_warm_storm():
    r = make_resort()
    cold = derive(make_model_data(t_sea_level=0.0, precip_mm_per_h=1.0, wind_kmh=10.0), r)
    warm = derive(make_model_data(t_sea_level=17.0, precip_mm_per_h=1.0, wind_kmh=10.0), r)
    assert cold.slr["summit"][0] > 15 > warm.slr["summit"][0]
    assert cold.snow["summit"][0] > 1.5 * warm.snow["summit"][0]


def test_model_without_profile_borrows_snow_level_from_donor():
    r = make_resort()
    full = derive(make_model_data("gfs_global", t_sea_level=15.5, rh=100.0, precip_mm_per_h=1.0), r)
    donor = make_donor([full])
    bare = make_model_data("ncep_nbm_conus", t_sea_level=15.5, rh=100.0, precip_mm_per_h=1.0, with_profile=False)
    alone = derive(bare, r)
    lent = derive(bare, r, donor)
    assert not alone.has_profile
    assert lent.snow_level[0] == pytest.approx(full.snow_level[0], abs=1)
    assert np.isfinite(alone.snow_level[0])               # surface fallback still works
    assert make_donor([alone]) is None


def _mds():
    return [
        make_model_data("gfs_global", n=312, start="2026-01-09T00", t_sea_level=6.0, precip_mm_per_h=0.5),
        make_model_data("ecmwf_ifs025", n=312, start="2026-01-09T00", t_sea_level=6.0, precip_mm_per_h=1.0),
        make_model_data("ncep_hrrr_conus", n=312, start="2026-01-09T00", t_sea_level=6.0,
                        precip_mm_per_h=2.0, valid_hours=72),
    ]


def test_build_resort_document_shape_and_dropout():
    r = make_resort()
    derived = [derive(m, r) for m in _mds()]
    doc = build_resort(r, derived, NOW, missing_models=["ncep_nbm_conus"])
    json.dumps(doc, allow_nan=False)                    # no NaN may leak into the published JSON

    assert len(doc["hourly"]["time"]) == 168
    assert doc["hourly"]["time"][0] == "2026-01-10T07:00Z"
    assert len(doc["daily"]) == 10                      # point values stop after ski day D+9
    assert all(e["kind"] == "point" for e in doc["daily"])
    assert doc["daily"][0]["date"] == "2026-01-09"      # 06:00 UTC is still Jan 9 in California
    day = doc["daily"][5]                               # past the HRRR horizon: constant weights
    assert day["snow_cm"]["mid"] == pytest.approx(day["snow_night_cm"]["mid"] + day["snow_day_cm"]["mid"], abs=0.15)
    assert day["snow_night_cm"]["mid"] == pytest.approx(2 * day["snow_day_cm"]["mid"], rel=0.05)  # 16 h vs 8 h
    assert day["snow_low_cm"]["mid"] <= day["snow_cm"]["mid"] <= day["snow_high_cm"]["mid"]
    assert day["quality"] in {"powder", "packed", "heavy"}
    # without ensemble data the range and confidence fall back to the model spread
    assert day["range_source"] == "models" and day["ens"] is None
    assert doc["ensemble"] is None and doc["outlook"] == []

    by = doc["by_model_daily_cm"]
    assert all(len(by[m][lv]) == 10 for m in by for lv in LEVELS)
    assert by["ncep_hrrr_conus"]["mid"][1] is not None and by["ncep_hrrr_conus"]["mid"][8] is None
    assert doc["daily"][8]["n_models"] == 2 and doc["daily"][8]["snow_cm"]["mid"] is not None

    status = {m["id"]: m["status"] for m in doc["models"]}
    assert status["ncep_nbm_conus"] == "missing" and status["gfs_global"] == "ok"
    hrrr = next(m for m in doc["models"] if m["id"] == "ncep_hrrr_conus")
    assert hrrr["horizon_h"] < 72

    s = doc["summary"]
    assert s["snow_24h_cm"]["mid"] < s["snow_72h_cm"]["mid"] < s["snow_7d_cm"]["mid"] < s["snow_16d_cm"]["mid"]
    assert s["snow_24h_cm"]["summit"] >= s["snow_24h_cm"]["base"]
    assert s["next_snow"]["date"] == doc["daily"][0]["date"]
    t = s["totals"]
    assert t["3d"]["cm"]["mid"] < t["7d"]["cm"]["mid"] and t["3d"]["low_cm"] is None
    assert t["16d"]["complete"] is False                # no ensemble -> nothing beyond day 10


def _ens_raw(start="2026-01-09", n_days=35, members=20, daily_cm=20.0, spread=True):
    """A synthetic ens/{id}.json: member i gets (i / mean) x daily_cm every day."""
    rows = []
    for i in range(members):
        f = (2.0 * i / (members - 1)) if spread else 1.0
        rows.append([round(daily_cm * f, 1)] * n_days)
    return {"schema_version": 2, "generated_at": "2026-01-10T05:00:00Z", "resort_id": "test-mountain",
            "elevation_m": 2300, "start_date": start,
            "models": {"gfs05": {"label": "GEFS", "weight": 1.0, "members": members, "daily": rows}}}


def test_build_resort_with_ensemble_publishes_ranges_probabilities_and_outlook():
    r = make_resort()
    derived = [derive(m, r) for m in _mds()]
    doc = build_resort(r, derived, NOW, ens_raw=_ens_raw(), tier="featured")
    json.dumps(doc, allow_nan=False)
    assert doc["resort"]["tier"] == "featured"

    daily = doc["daily"]
    assert [e["kind"] for e in daily] == ["point"] * 10 + ["prob"] * 6
    # beyond day 10 there is no point value, only percentiles and probabilities
    far = daily[12]
    assert "snow_cm" not in far and set(far["ens"]["prob"]) == {"2.5", "15"}
    assert 0.0 <= far["ens"]["prob"]["15"]["mid"] <= far["ens"]["prob"]["2.5"]["mid"] <= 1.0
    assert far["ens"]["p10"]["mid"] <= far["ens"]["p50"]["mid"] <= far["ens"]["p90"]["mid"]
    assert far["ens"]["n_members"] == 20

    day = daily[5]
    assert day["range_source"] == "ensemble"
    assert day["snow_low_cm"]["mid"] <= day["snow_cm"]["mid"] <= day["snow_high_cm"]["mid"]
    assert day["snow_low_cm"]["mid"] < day["snow_high_cm"]["mid"]
    assert day["confidence"] in {"high", "medium", "low"} and 0.0 <= day["ens"]["agreement"] <= 1.0

    # the ensemble is calibrated so that its mean matches the blend over the point period
    cal = doc["ensemble"]["calibration"]
    assert cal["days"] == 10 and cal["blend_cm"] > 0
    blend_total = sum(e["snow_cm"]["mid"] for e in daily[:10])
    ens_total = sum(e["ens"]["mean"]["mid"] for e in daily[:10])
    assert ens_total == pytest.approx(blend_total, rel=0.03)
    assert doc["ensemble"]["models"] == [{"id": "gfs05", "label": "GEFS", "members": 20, "horizon_days": 35}]

    out = doc["outlook"]
    assert [o["week"] for o in out] == [3, 4, 5]
    assert out[0]["start"] == "2026-01-23" and out[0]["end"] == "2026-01-29"
    for o in out:
        assert o["p10_cm"] <= o["p50_cm"] <= o["p90_cm"] and o["models"] == ["gfs05"]
        assert 1.0 >= o["prob"]["15"] >= o["prob"]["30"] >= o["prob"]["60"] >= 0.0

    t = doc["summary"]["totals"]
    assert t["16d"]["complete"] and t["16d"]["cm"]["mid"] > t["7d"]["cm"]["mid"] > t["3d"]["cm"]["mid"]
    for k in ("3d", "7d", "16d"):
        assert t[k]["low_cm"]["mid"] <= t[k]["cm"]["mid"] <= t[k]["high_cm"]["mid"]
    assert doc["summary"]["snow_16d_cm"] == t["16d"]["cm"]


def test_stale_ensemble_file_is_realigned_by_date():
    r = make_resort()
    derived = [derive(m, r) for m in _mds()]
    # the cached member totals start two days before "today": the first two days are simply dropped
    doc = build_resort(r, derived, NOW, ens_raw=_ens_raw(start="2026-01-07"))
    assert doc["daily"][0]["ens"]["n_members"] == 20
    assert len(doc["daily"]) == 16
    assert [o["week"] for o in doc["outlook"]] == [3, 4]     # week 5 is no longer covered


def test_high_resolution_model_dominates_early_then_drops_out():
    r = make_resort()
    lo = derive(make_model_data("gfs_global", n=312, start="2026-01-09T00", t_sea_level=6.0, precip_mm_per_h=1.0), r)
    hi = derive(make_model_data("ncep_hrrr_conus", n=312, start="2026-01-09T00", t_sea_level=6.0,
                                precip_mm_per_h=3.0, valid_hours=72), r)
    h = build_resort(r, [lo, hi], NOW)["hourly"]["precip_mm"]
    assert h[0] == pytest.approx((1.0 * 1.5 + 3.0 * 3.0) / 4.5, abs=0.01)   # 0-48 h weights 1.5 : 3
    assert h[100] == pytest.approx(1.0)                                      # HRRR gone, GFS alone


def test_index_and_manifest():
    db = load_resorts()
    r = make_resort()
    doc = build_resort(r, [derive(make_model_data(n=312, start="2026-01-09T00", precip_mm_per_h=0.2), r)], NOW,
                       ens_raw=_ens_raw())
    index = build_index(db.regions, [doc], NOW)
    row = index["resorts"][0]
    assert row["id"] == "test-mountain" and len(row["dates"]) == 10
    assert row["tier"] == "standard" and row["n_members"] == 20
    assert row["generated_at"] == "2026-01-10T06:00:00Z" and row["ensemble_at"] == "2026-01-10T05:00:00Z"
    assert [o["week"] for o in row["outlook"]] == [3, 4, 5]
    man = build_manifest(NOW, {"gfs_global": {"label": "GFS", "status": "ok"}}, 1,
                         {"requests": 3, "weighted_calls": 12.34, "by_kind": {"ensemble": 7.75}},
                         {"gfs05": {"label": "GEFS", "status": "ok"}}, {"mode": "auto"}, {"total": 7000.0})
    assert man["generated_at"] == "2026-01-10T06:00:00Z" and man["api_usage"]["weighted_calls"] == 12.3
    assert man["api_usage"]["daily_estimate"]["total"] == 7000.0 and man["api_usage"]["daily_target"] == 8000
    assert man["ensembles"][0]["id"] == "gfs05" and man["run"]["mode"] == "auto"
    assert "Open-Meteo" in man["attribution"]
    json.dumps([index, man], allow_nan=False)


def test_no_models_is_an_error():
    with pytest.raises(ValueError):
        build_resort(make_resort(), [], NOW)
