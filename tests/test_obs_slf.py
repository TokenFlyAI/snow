"""SLF IMIS observations (pipeline/verify/obs_slf.py), the source dispatch and the archive backfill."""
from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline.publish import obs_docs
from pipeline.verify import archive, obs_slf
from pipeline.verify.obs import HourlySeries

UTC = timezone.utc
START = datetime(2026, 1, 10, 0, tzinfo=UTC)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_parse_depth_temp_and_running_precip():
    meas = [{"measure_date": iso(START + timedelta(minutes=30 * k)), "HS": 50.0 + k, "TA_30MIN_MEAN": -3.0}
            for k in range(8)]                                  # 00:00 .. 03:30
    prec = [{"measure_date": iso(START + timedelta(minutes=10 * k)), "RR_10MIN_SUM": 0.5} for k in range(1, 13)]
    s = obs_slf.parse(meas, prec, START, 4)
    assert list(s.values["depth_cm"]) == [50.0, 52.0, 54.0, 56.0]          # on the hour only
    assert list(s.values["temp_c"]) == [-3.0] * 4
    # 10-min sums ending 00:10 .. 02:00: 6 x 0.5 in hour 1, 6 x 0.5 in hour 2
    assert list(s.values["precip_mm"]) == [0.0, 3.0, 6.0, 6.0]


def test_parse_without_gauge_gives_no_precip():
    s = obs_slf.parse([{"measure_date": iso(START), "HS": 10.0}], None, START, 3)
    assert np.isnan(s.values["precip_mm"]).all() and s.values["depth_cm"][0] == 10.0


def test_fetch_all_sends_each_station_to_its_source(monkeypatch):
    seen = {}

    def fake(name):
        def f(ids, offsets, start, end):
            seen[name] = sorted(ids)
            if name == "slf":
                raise RuntimeError("down")
            return {i: HourlySeries(start=start, values={}) for i in ids}
        return f
    monkeypatch.setattr(obs_docs.obs_snotel, "fetch", fake("snotel"))
    monkeypatch.setattr(obs_docs.obs_slf, "fetch", fake("slf"))
    got = obs_docs.fetch_all(["SLF:GOR2", "1040:CO:SNTL"], {}, START, START)
    assert seen == {"snotel": ["1040:CO:SNTL"], "slf": ["SLF:GOR2"]}
    assert list(got) == ["1040:CO:SNTL"]                      # one source down keeps the other
    assert obs_docs.source_of("SLF:GOR2") == obs_slf.SOURCE


class R:
    id, timezone = "zermatt", "Europe/Zurich"


def test_days_older_than_the_live_window_come_from_the_archive(tmp_path):
    now = datetime(2026, 1, 20, 12, tzinfo=UTC)
    stations = {"zermatt": [{"triplet": "SLF:GOR2", "name": "Gornergratsee", "grade": "A"}]}

    def fetch(ids, offsets, start, end):                       # data for the last 3 days only
        n = int((end - start).total_seconds() // 3600) + 1
        depth = np.full(n, np.nan)
        depth[-72:] = 80.0
        return {"SLF:GOR2": HourlySeries(start=start, values={"depth_cm": depth})}
    past = {("zermatt", "SLF:GOR2", "2026-01-10"): {"snow_cm": 25.0, "depth_cm": 70.0, "flags": []}}
    doc = obs_docs.build_obs_docs([R], stations, now, fetch, past)["zermatt"]
    days = {d["date"]: d for d in doc["stations"][0]["days"]}
    assert days["2026-01-10"]["snow_cm"] == 25.0 and days["2026-01-10"]["complete"]
    assert days["2026-01-12"]["snow_cm"] is None              # outside the live window, nothing archived
    assert doc["stations"][0]["source"] == obs_slf.SOURCE and doc["source"] == obs_slf.SOURCE

    # the archive keeps a good day when a later run has nothing for it
    archive.write_obs(tmp_path, [{"resort_id": "zermatt", "stations": [{"triplet": "SLF:GOR2", "grade": "A", "days": [
        {"date": "2026-01-12", "complete": True, "snow_cm": 10.0, "flags": []}]}]}])
    archive.write_obs(tmp_path, [doc])
    rows = [r for r in archive.read_obs(tmp_path) if r["target_date"] == "2026-01-12"]
    assert len(rows) == 1 and rows[0]["snow_cm"] == 10.0
