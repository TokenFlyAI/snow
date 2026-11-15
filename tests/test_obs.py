"""Observed ski days from hourly SNOTEL readings (pipeline/verify/obs.py, obs_snotel.py, publish/obs_docs.py)."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from pipeline.publish.obs_docs import build_obs_docs
from pipeline.run import publish_obs
from pipeline.state import Previous
from pipeline.verify import obs_snotel
from pipeline.verify.obs import (DEPTH_DEADBAND_CM, HourlySeries, gain, monotone, rolling_median, ski_days,
                                 window_edges)

FIX = Path(__file__).parent / "fixtures" / "snotel_784_2024_03_hourly.json"
UTC = timezone.utc


# ---- time windows -------------------------------------------------------------------------------

def test_ski_day_window_in_utc():
    # 16:00 PST = 00:00 UTC; 08:00 PST = 16:00 UTC
    assert window_edges(date(2024, 3, 1), "America/Los_Angeles") == (
        datetime(2024, 3, 1, 0, tzinfo=UTC), datetime(2024, 3, 1, 16, tzinfo=UTC), datetime(2024, 3, 2, 0, tzinfo=UTC))


def test_ski_day_window_across_the_daylight_saving_change():
    # Denver switches to MDT on 8 Mar 2026 at 02:00: the window starts at 16:00 MST (23:00Z) on the 7th
    # for the 8th, and at 16:00 MDT (22:00Z) on the 8th for the 9th
    assert window_edges(date(2026, 3, 8), "America/Denver")[0] == datetime(2026, 3, 7, 23, tzinfo=UTC)
    assert window_edges(date(2026, 3, 9), "America/Denver")[0] == datetime(2026, 3, 8, 22, tzinfo=UTC)
    assert window_edges(date(2026, 3, 9), "America/Denver")[2] == datetime(2026, 3, 9, 22, tzinfo=UTC)


def test_station_time_is_a_fixed_offset():
    payload = [{"stationTriplet": "1:CA:SNTL", "data": [{"stationElement": {"elementCode": "SNWD"},
                                                         "values": [{"date": "2024-07-01 00:00", "value": 10}]}]},
               {"stationTriplet": "2:AK:SNTL", "data": [{"stationElement": {"elementCode": "PREC"},
                                                         "values": [{"date": "2024-07-01 00:00", "value": 1.0}]}]}]
    start = datetime(2024, 7, 1, 0, tzinfo=UTC)
    s = obs_snotel.parse(payload, {"1:CA:SNTL": -8.0, "2:AK:SNTL": -9.0}, start, 24)
    # no daylight saving: midnight station time is 08:00Z in July for the lower 48, 09:00Z in Alaska
    assert np.nanargmax(s["1:CA:SNTL"].values["depth_cm"]) == 8
    assert s["1:CA:SNTL"].values["depth_cm"][8] == pytest.approx(25.4)
    assert np.nanargmax(s["2:AK:SNTL"].values["precip_mm"]) == 9
    assert s["2:AK:SNTL"].values["precip_mm"][9] == pytest.approx(25.4)


# ---- filters ------------------------------------------------------------------------------------

def test_median_removes_a_single_hour_spike():
    v = np.array([170.0, 170, 475, 170, 172, np.nan, 172])
    assert np.nanmax(rolling_median(v, 5)) < 180


def test_gain_ignores_jitter_and_counts_snow_after_settling():
    inch = 2.54
    assert gain(np.array([70, 71, 70, 71, 70, 71]) * inch, DEPTH_DEADBAND_CM) == pytest.approx(inch)
    # settles 5 in, then 5 in of new snow
    assert gain(np.array([100, 98, 95, 97, 100]) * inch, DEPTH_DEADBAND_CM) == pytest.approx(5 * inch)


def test_monotone_gauge_and_its_yearly_reset():
    v = np.array([500.0, 505, 503, 510, np.nan, 2, 4, 3])
    assert list(monotone(v)[[0, 1, 2, 3, 5, 6, 7]]) == [500, 505, 505, 510, 2, 4, 4]


# ---- a real storm -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def blizzard():
    start = datetime(2024, 2, 27, 8, tzinfo=UTC)
    s = obs_snotel.parse(json.loads(FIX.read_text()), {"784:CA:SNTL": -8.0}, start, 24 * 9)["784:CA:SNTL"]
    dates = [date(2024, 2, 28) + timedelta(days=i) for i in range(8)]
    return {d.date: d for d in ski_days(s, "America/Los_Angeles", dates, datetime(2024, 3, 10, tzinfo=UTC))}


def test_blizzard_liquid_total_matches_the_daily_gauge(blizzard):
    # tests/test_backtest.py: the daily gauge readings give 208.3 mm for 28 Feb - 5 Mar
    total = sum(blizzard[d].precip_mm for d in blizzard if "2024-02-28" <= d <= "2024-03-05")
    assert total == pytest.approx(208.3, abs=3.0)
    assert all(blizzard[d].precip_mm >= blizzard[d].precip_night_mm for d in blizzard)


def test_blizzard_new_snow(blizzard):
    assert blizzard["2024-02-28"].snow_cm == 0          # dry day: depth jitter is not snow
    assert blizzard["2024-03-01"].snow_cm > 30
    two_days = blizzard["2024-03-01"].snow_cm + blizzard["2024-03-02"].snow_cm
    assert 60 <= two_days <= 100                        # depth 170 -> 216 cm, plus settling
    # the depth fell while it was still snowing: not usable for new snow
    assert "depth_fell" in blizzard["2024-03-03"].flags
    assert blizzard["2024-03-01"].temp_max_c < 0


# ---- published documents ------------------------------------------------------------------------

class _R:
    def __init__(self, rid, tz="America/Los_Angeles"):
        self.id, self.timezone = rid, tz


STATIONS = {"a": [{"triplet": "1:CA:SNTL", "name": "One", "elevation_m": 2400, "utc_offset_h": -8, "km": 1.0,
                   "dz_m": 50, "grade": "A"}]}


def _fake_fetch(triplets, offsets, start, end):
    hours = int((end - start).total_seconds() // 3600) + 1
    prec = np.linspace(100.0, 150.0, hours)          # 50 mm spread over the period
    depth = np.linspace(50.0, 90.0, hours)
    return {t: HourlySeries(start, {"precip_mm": prec, "swe_mm": np.full(hours, np.nan),
                                    "depth_cm": depth, "temp_c": np.full(hours, -5.0)}) for t in triplets}


def test_obs_document():
    now = datetime(2026, 11, 15, 20, 30, tzinfo=UTC)       # 12:30 PST: today's ski day is under way
    docs = build_obs_docs([_R("a"), _R("b")], STATIONS, now, _fake_fetch)
    assert list(docs) == ["a"]
    days = docs["a"]["stations"][0]["days"]
    assert len(days) == 14 and days[-1]["date"] == "2026-11-15" and days[-1]["complete"] is False
    assert all(d["complete"] for d in days[:-1])
    assert days[-2]["precip_mm"] == pytest.approx(50.0 / 13.4, rel=0.2)
    assert docs["a"]["schema_version"] == 2 and docs["a"]["stations"][0]["grade"] == "A"


def test_after_lifts_close_the_next_ski_day_is_listed():
    now = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)         # 17:00 PST on the 15th
    days = build_obs_docs([_R("a")], STATIONS, now, _fake_fetch)["a"]["stations"][0]["days"]
    assert days[-1]["date"] == "2026-11-16" and days[-1]["complete"] is False
    assert days[-2]["date"] == "2026-11-15" and days[-2]["complete"] is True


def test_publish_keeps_the_previous_files_when_the_fetch_fails(tmp_path):
    prev_dir = tmp_path / "prev"
    (prev_dir / "obs").mkdir(parents=True)
    old = {"schema_version": 2, "resort_id": "a", "generated_at": "2026-11-15T00:00:00Z", "stations": []}
    (prev_dir / "obs" / "a.json").write_text(json.dumps(old))

    def broken(*a, **k):
        raise RuntimeError("AWDB down")

    out = tmp_path / "out"
    info = publish_obs(out, [_R("a")], STATIONS, datetime(2026, 11, 15, 20, tzinfo=UTC), Previous(str(prev_dir)), broken)
    assert info == {"status": "previous", "resorts": 1, "resorts_with_stations": 1}
    assert json.loads((out / "obs" / "a.json").read_text()) == old
