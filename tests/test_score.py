"""A3 scoring (pipeline/verify/score.py) and the observation archive (archive.write_obs / read_obs)."""
from datetime import date, datetime, timezone

import pytest

from pipeline.verify import archive
from pipeline.verify.score import best_obs, build_verification, latest_forecasts, season_start

UTC = timezone.utc
NOW = datetime(2026, 12, 20, 12, tzinfo=UTC)


def fc_row(rid, day, lead, issued, snow, precip=10.0, low=None, high=None, p15=None, p10=None, p90=None,
           by_model=None, kind="point"):
    return {"issued_at": issued, "resort_id": rid, "target_date": day, "lead_days": lead, "kind": kind,
            "snow_cm": {"base": snow, "mid": snow, "summit": snow}, "precip_mm": precip,
            "snow_low_cm": {"mid": low} if low is not None else None,
            "snow_high_cm": {"mid": high} if high is not None else None,
            "by_model": by_model or {}, "ens": {"p10": p10, "p90": p90, "p_15": p15, "p_2_5": None}}


def write_fc(root, issued: datetime, rows):
    archive._write_gz(archive.path_for(root, issued), rows)


def obs_doc(rid, triplet, grade, days):
    return {"resort_id": rid, "stations": [{"triplet": triplet, "grade": grade, "days": days}]}


def obs_day(day, snow, precip=10.0, flags=(), complete=True):
    return {"date": day, "complete": complete, "precip_mm": precip, "precip_night_mm": None, "swe_gain_mm": None,
            "snow_cm": snow, "snow_night_cm": None, "depth_cm": 50.0, "temp_min_c": -5, "temp_max_c": -1,
            "flags": list(flags)}


def test_season_start():
    assert season_start(date(2026, 12, 1)) == date(2026, 9, 1)
    assert season_start(date(2027, 3, 1)) == date(2026, 9, 1)


def test_the_last_forecast_for_a_lead_is_scored():
    rows = [fc_row("a", "2026-12-10", 1, "2026-12-09T02:00:00Z", 5),
            fc_row("a", "2026-12-10", 1, "2026-12-09T20:00:00Z", 9),
            fc_row("a", "2026-12-10", 2, "2026-12-08T20:00:00Z", 3)]
    f = latest_forecasts(rows)
    assert f[("a", "2026-12-10", 1)]["snow_cm"]["mid"] == 9 and len(f) == 2


def test_best_scored_station_with_data():
    rows = [{"resort_id": "a", "target_date": "d", "rank": 0, "grade": "A", "precip_mm": None, "snow_cm": None},
            {"resort_id": "a", "target_date": "d", "rank": 1, "grade": "B", "precip_mm": 3.0, "snow_cm": 2.0},
            {"resort_id": "b", "target_date": "d", "rank": 0, "grade": "C", "precip_mm": 3.0, "snow_cm": 2.0}]
    o = best_obs(rows)
    assert o[("a", "d")]["rank"] == 1 and ("b", "d") not in o


def test_obs_archive_rewrites_a_day_and_keeps_other_resorts(tmp_path):
    archive.write_obs(tmp_path, [obs_doc("a", "1:CA:SNTL", "A", [obs_day("2026-12-10", 5), obs_day("2026-12-11", 1, complete=False)]),
                                 obs_doc("b", "2:CA:SNTL", "B", [obs_day("2026-12-10", 7)])])
    # a later run: station 1 revised its reading, station 2 did not answer
    archive.write_obs(tmp_path, [obs_doc("a", "1:CA:SNTL", "A", [obs_day("2026-12-10", 6)])])
    rows = list(archive.read_obs(tmp_path))
    assert [(r["resort_id"], r["snow_cm"]) for r in rows] == [("a", 6), ("b", 7)]   # the incomplete day is not archived
    assert archive.obs_path(tmp_path, "2026-12-10").exists() and (tmp_path / "README.md").exists()


@pytest.fixture
def scored(tmp_path):
    # resort a: two days, NBM in the blend; resort b: one day whose depth fell in the storm
    write_fc(tmp_path, datetime(2026, 12, 9, 20, tzinfo=UTC), [
        fc_row("a", "2026-12-10", 1, "2026-12-09T20:00:00Z", 20, precip=20, low=10, high=30, p15=0.8, p10=12, p90=28,
               by_model={"ncep_nbm_conus": 30, "gfs_global": 10}),
        fc_row("a", "2026-12-11", 2, "2026-12-09T20:00:00Z", 4, precip=5, low=0, high=3, p15=0.1,
               by_model={"ncep_nbm_conus": 2}),
        fc_row("b", "2026-12-10", 1, "2026-12-09T20:00:00Z", 30, p15=0.9),
        fc_row("a", "2026-12-21", 10, "2026-12-09T20:00:00Z", None, kind="prob", p15=0.3),
    ])
    write_fc(tmp_path, datetime(2026, 11, 1, 2, tzinfo=UTC), [   # season window only
        fc_row("a", "2026-11-02", 1, "2026-11-01T02:00:00Z", 10)])
    archive.write_obs(tmp_path, [
        obs_doc("a", "1:CA:SNTL", "A", [obs_day("2026-12-10", 16, precip=18), obs_day("2026-12-11", 0, precip=1),
                                        obs_day("2026-11-02", 6)]),
        obs_doc("b", "2:CA:SNTL", "B", [obs_day("2026-12-10", 5, flags=["depth_fell"])]),
    ])
    return build_verification(tmp_path, {"a": "tahoe", "b": "utah"}, NOW)


def test_snow_and_precip_errors(scored):
    lead1 = scored["windows"]["season"]["regions"]["tahoe"]["leads"]["1"]
    # a: 20 vs 16 on 10 Dec, 10 vs 6 on 2 Nov -> MAE 4, bias +4
    assert lead1["snow_mae_cm"] == 4.0 and lead1["snow_bias_cm"] == 4.0 and lead1["snow_n"] == 2
    assert lead1["precip_mae_mm"] == pytest.approx(1.0)          # |20-18| and |10-10|
    assert lead1["big"] == {"hits": 1, "misses": 0, "false_alarms": 0, "csi": 1.0}
    assert lead1["coverage"] == {"range": 1.0, "ensemble_10_90": 1.0}
    assert lead1["brier_15"] == pytest.approx(0.04)                # (0.8 - 1)^2


def test_depth_fell_days_are_not_scored_for_snow(scored):
    b = scored["windows"]["season"]["resorts"]["b"]["leads"]["1"]
    assert "snow_mae_cm" not in b and "brier_15" not in b and b["precip_n"] == 1


def test_models_and_skill_against_nbm(scored):
    lead2 = scored["windows"]["season"]["resorts"]["a"]["leads"]["2"]
    assert lead2["coverage"]["range"] == 1.0                       # 0 cm observed, range 0-3: inside
    lead1 = scored["windows"]["season"]["resorts"]["a"]["leads"]["1"]
    assert lead1["models"]["ncep_nbm_conus"] == {"n": 1, "snow_mae_cm": 14.0, "ours_snow_mae_cm": 4.0}
    assert lead1["skill_vs_nbm"] == pytest.approx(1 - 4 / 14, abs=1e-3)


def test_windows(scored):
    w30, season = scored["windows"]["30d"], scored["windows"]["season"]
    assert (w30["start"], w30["end"]) == ("2026-11-20", "2026-12-19")
    assert season["start"] == "2026-09-01"
    assert w30["overall"]["leads"]["1"]["snow_n"] == 1              # 2 Nov is outside the last 30 days
    assert season["overall"]["leads"]["1"]["snow_n"] == 2
    assert scored["windows"]["season"]["ski_days"] == 3 and scored["windows"]["season"]["n_resorts"] == 2
    assert set(scored["windows"]["season"]["resorts"]) == {"a", "b"}
    assert "10" not in season["overall"]["leads"]                   # 21 Dec has not been observed yet


def test_recent_pairs(scored):
    rec = {(r["resort_id"], r["date"]): r for r in scored["recent"]}
    assert set(rec) == {("a", "2026-12-10"), ("a", "2026-12-11"), ("b", "2026-12-10")}     # 2 Nov is older than 30 days
    a = rec[("a", "2026-12-10")]
    assert a["obs_snow_cm"] == 16 and a["forecast"]["1"]["snow_cm"] == 20 and a["forecast"]["1"]["high_cm"] == 30
    assert "3" not in a["forecast"] and rec[("b", "2026-12-10")]["flags"] == ["depth_fell"]
