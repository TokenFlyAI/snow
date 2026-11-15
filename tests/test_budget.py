"""API budget: the shipped resort list and featured list must fit the Open-Meteo free tier."""
import pytest

from pipeline.config import (API_DAILY_LIMIT, API_DAILY_TARGET, ENSEMBLES, MODEL_BY_ID, call_weight, current_slot,
                             ensembles_for, estimate_daily_calls, load_featured, models_for, refresh_slot)
from pipeline.ingest import open_meteo as om
from pipeline.resorts import load_resorts
from tests.helpers import make_resort


def test_shipped_configuration_stays_under_the_daily_target():
    db = load_resorts()
    featured = load_featured()
    assert set(featured) <= {r.id for r in db.resorts}, "data/featured.yaml lists an unknown resort"
    assert len(featured) == len(set(featured))
    est = estimate_daily_calls(db.resorts, featured, len(om.hourly_vars()))
    assert est["total"] < API_DAILY_TARGET < API_DAILY_LIMIT, est
    assert est["total"] == pytest.approx(est["featured_deterministic"] + est["standard_deterministic"] + est["ensembles"], abs=0.5)


def test_call_weights_match_the_free_tier_rules():
    # deterministic: 29 hourly variables over 13 days -> 2.9 calls per model and location
    assert call_weight(len(om.hourly_vars()), 13) == pytest.approx(2.9)
    # ensembles: every member counts as a variable
    assert call_weight(31, 35) == pytest.approx(7.75)      # GEFS, 35 days
    assert call_weight(51, 15) == pytest.approx(5.46, abs=0.01)
    assert call_weight(40, 8) == pytest.approx(4.0)


def test_standard_tier_gets_the_global_models_plus_one_regional_and_one_ensemble():
    glob = {"ecmwf_ifs025", "gfs_global", "icon_seamless", "gem_global"}
    us = make_resort()
    assert {m.id for m in models_for(us, "standard")} == glob | {"ncep_nbm_conus"}
    assert len(models_for(us, "featured")) == 8
    ch = make_resort(country="CH", state=None, timezone="Europe/Zurich")
    assert {m.id for m in models_for(ch, "standard")} == glob | {"meteofrance_seamless"}
    jp = make_resort(country="JP", state="Nagano", timezone="Asia/Tokyo")
    assert {m.id for m in models_for(jp, "standard")} == glob | {"jma_seamless"}
    nz = make_resort(country="NZ", state=None, timezone="Pacific/Auckland")
    assert {m.id for m in models_for(nz, "standard")} == glob | {"ukmo_seamless"}
    ca = make_resort(country="CA", state="BC", timezone="America/Vancouver")
    assert {m.id for m in models_for(ca, "standard")} == glob | {"gem_hrdps_continental"}
    ak = make_resort(state="AK", timezone="America/Anchorage")
    assert {m.id for m in models_for(ak, "standard")} == glob                     # no regional model up there
    for r in (us, ch, jp, nz, ca, ak):
        assert set(models_for(r, "standard")) <= set(models_for(r, "featured"))
    for r in load_resorts().resorts:
        assert 4 <= len(models_for(r, "standard")) <= 5, r.id
    assert [e.id for e in ensembles_for("standard")] == ["gfs05"]
    assert [e.id for e in ensembles_for("featured")] == [e.id for e in ENSEMBLES]


def test_european_regional_models():
    fr = {m.id for m in models_for(make_resort(country="FR", state=None, timezone="Europe/Paris"))}
    at = {m.id for m in models_for(make_resort(country="AT", state=None, timezone="Europe/Vienna"))}
    ad = {m.id for m in models_for(make_resort(country="AD", state=None, timezone="Europe/Andorra"))}
    assert {"meteofrance_seamless", "meteoswiss_icon_seamless", "ukmo_seamless", "icon_seamless"} <= fr
    assert "meteoswiss_icon_seamless" in at and "meteoswiss_icon_seamless" not in ad
    assert "meteofrance_seamless" in ad and "ncep_nbm_conus" not in fr
    for mid in ("meteofrance_seamless", "meteoswiss_icon_seamless", "ukmo_seamless"):
        assert mid in MODEL_BY_ID
    # the model chart has 8 fixed colour slots: no resort may get more models than that
    for r in load_resorts().resorts:
        assert len(models_for(r, "featured")) <= 8, r.id


def test_refresh_slots_follow_the_local_morning():
    assert refresh_slot(7.7) == 2           # Zermatt: 03:37 local
    assert refresh_slot(-72.8) == 8         # Vermont: 03:37 local
    assert refresh_slot(-70.2) == 8         # Chile
    assert refresh_slot(-120.2) == 14       # Tahoe: 06:37 local
    assert refresh_slot(-105.9) == 14       # Colorado
    assert refresh_slot(140.7) == 20        # Niseko: 05:37 local
    assert refresh_slot(148.4) == 20 and refresh_slot(168.7) == 20
    # a run belongs to the slot at or before its start hour, so a delayed cron still counts
    assert [current_slot(h) for h in (2, 3, 7, 8, 13, 14, 19, 20, 23, 0, 1)] == [2, 2, 2, 8, 8, 14, 14, 20, 20, 20, 20]


def test_rate_limiter_waits_for_the_minute_window():
    clock = {"t": 0.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    lim = om.RateLimiter(per_minute=300, clock=lambda: clock["t"], sleep=sleep)
    lim.acquire(200)
    lim.acquire(100)
    assert sleeps == []                      # 300 of 300 used, no waiting yet
    lim.acquire(150)                         # would be 450 in the same minute
    assert sleeps and sum(sleeps) >= 60.0    # waited until the first calls left the window
    big = om.RateLimiter(per_minute=100, clock=lambda: clock["t"], sleep=sleep)
    big.acquire(500)                         # a single oversized request is let through alone


def test_rate_limiter_respects_the_hourly_limit():
    clock = {"t": 0.0}

    def sleep(s):
        clock["t"] += s

    lim = om.RateLimiter(per_minute=1000, per_hour=1000, clock=lambda: clock["t"], sleep=sleep)
    for _ in range(10):
        lim.acquire(100)
        clock["t"] += 61.0                   # spread over ten minutes: minute limit never binds
    start = clock["t"]
    lim.acquire(100)                         # the hour is full: wait for the first call to age out
    assert clock["t"] - start >= 3600.0 - 10 * 61.0 - 1
