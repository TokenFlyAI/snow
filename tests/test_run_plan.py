"""What a run refreshes, and that it starts from the previously published files."""
import json
from datetime import datetime, timedelta, timezone

from pipeline.run import plan
from pipeline.state import Previous, age_hours
from tests.helpers import make_resort

FMT = "%Y-%m-%dT%H:%M:%SZ"
NOW = datetime(2026, 1, 10, 14, 40, tzinfo=timezone.utc)        # the 14:37 UTC run = slot 14 (western North America)


def _row(r, tier, doc_age_h, ens_age_h):
    return {"id": r.id, "tier": tier,
            "generated_at": (NOW - timedelta(hours=doc_age_h)).strftime(FMT),
            "ensemble_at": (NOW - timedelta(hours=ens_age_h)).strftime(FMT)}


def _resorts():
    return [make_resort(id="tahoe-featured"),                                    # lon -120: slot 14
            make_resort(id="tahoe-standard"),
            make_resort(id="vermont", lon=-72.8, state="VT", timezone="America/New_York"),   # slot 8
            make_resort(id="zermatt", lon=7.7, lat=46.0, country="CH", state=None, timezone="Europe/Zurich")]


def _by_id(tasks):
    return {t.resort.id: t for t in tasks}


def test_scheduled_run_refreshes_featured_and_the_due_region_only():
    rs = _resorts()
    prev = {"resorts": [_row(rs[0], "featured", 6, 24), _row(rs[1], "standard", 24, 24),
                        _row(rs[2], "standard", 6, 6), _row(rs[3], "standard", 12, 12)]}
    t = _by_id(plan(rs, {"tahoe-featured"}, prev, NOW))
    assert (t["tahoe-featured"].det, t["tahoe-featured"].ens) == (True, True)    # its daily ensemble slot
    assert (t["tahoe-standard"].det, t["tahoe-standard"].ens) == (True, True)    # due now
    assert (t["vermont"].det, t["vermont"].ens) == (False, False)                # refreshed 6 h ago, carried over
    assert (t["zermatt"].det, t["zermatt"].ens) == (False, False)
    assert t["vermont"].why == "carried" and t["tahoe-standard"].why == "due"


def test_featured_resort_outside_its_slot_only_gets_deterministic_models():
    rs = _resorts()
    prev = {"resorts": [_row(rs[0], "featured", 6, 6), _row(rs[1], "standard", 6, 6),
                        _row(rs[2], "standard", 6, 6), _row(rs[3], "standard", 6, 6)]}
    later = NOW + timedelta(hours=6)                                             # the 20:37 run
    t = _by_id(plan(rs, {"tahoe-featured"}, prev, later))
    assert (t["tahoe-featured"].det, t["tahoe-featured"].ens) == (True, False)
    assert not any(x.det for k, x in t.items() if k != "tahoe-featured")


def test_missing_stale_and_retiered_resorts_are_refreshed_out_of_turn():
    rs = _resorts()
    prev = {"resorts": [_row(rs[0], "standard", 3, 3),        # was standard, now featured
                        _row(rs[3], "standard", 31, 31)]}     # its own run failed yesterday
    t = _by_id(plan(rs, {"tahoe-featured"}, prev, NOW))
    assert t["tahoe-featured"].why == "tier changed" and t["tahoe-featured"].ens
    assert t["tahoe-standard"].why == "new" and t["vermont"].why == "new"
    assert t["zermatt"].det and t["zermatt"].ens and t["zermatt"].why == "stale"


def test_a_second_run_in_the_same_slot_does_not_repeat_the_daily_refresh():
    rs = _resorts()
    prev = {"resorts": [_row(r, "standard", 1, 1) for r in rs]}
    t = _by_id(plan(rs, set(), prev, NOW))
    assert not any(x.det or x.ens for x in t.values())


def test_a_full_run_earlier_today_is_not_repeated_in_the_regional_slot():
    rs = _resorts()
    prev = {"resorts": [_row(r, "standard", 10, 10) for r in rs]}               # e.g. the first deploy, 10 h ago
    t = _by_id(plan(rs, set(), prev, NOW))
    assert not t["tahoe-standard"].det and not t["tahoe-standard"].ens         # due, but fresh enough
    later = _by_id(plan(rs, set(), {"resorts": [_row(r, "standard", 23, 23) for r in rs]}, NOW))
    assert later["tahoe-standard"].det and later["tahoe-standard"].ens         # the normal daily rhythm


def test_a_skipped_slot_is_caught_up_by_the_next_run():
    # GitHub drops scheduled runs: the 02:37 run (Europe) never came, the next one starts at 09:19
    rs = _resorts()
    late = datetime(2026, 1, 10, 9, 19, tzinfo=timezone.utc)
    prev = {"resorts": [{"id": r.id, "tier": "standard",
                         "generated_at": (late - timedelta(hours=24)).strftime(FMT),
                         "ensemble_at": (late - timedelta(hours=24)).strftime(FMT)} for r in rs]}
    prev["resorts"][1]["generated_at"] = prev["resorts"][1]["ensemble_at"] = "2026-01-09T15:00:00Z"  # Tahoe: yesterday's slot
    t = _by_id(plan(rs, set(), prev, late))
    assert t["zermatt"].det and t["zermatt"].ens and t["zermatt"].why == "due"     # slot 02 opened since
    assert t["vermont"].det and t["vermont"].ens                                    # its own slot (08)
    assert not t["tahoe-standard"].det                                              # slot 14 has not opened yet
    # once caught up, the following runs leave it alone until 02:00 UTC tomorrow
    done = {"resorts": [{**row, "generated_at": late.strftime(FMT), "ensemble_at": late.strftime(FMT)}
                        for row in prev["resorts"]]}
    for h in (6, 11, 16):
        assert not _by_id(plan(rs, set(), done, late + timedelta(hours=h)))["zermatt"].det
    assert _by_id(plan(rs, set(), done, late + timedelta(hours=17, minutes=30)))["zermatt"].det   # 02:49 next day


def test_full_and_featured_modes():
    rs = _resorts()
    prev = {"resorts": [_row(rs[0], "featured", 1, 1)] + [_row(r, "standard", 20, 20) for r in rs[1:]]}
    assert all(x.det and x.ens for x in plan(rs, {"tahoe-featured"}, prev, NOW, mode="full"))
    t = _by_id(plan(rs, {"tahoe-featured"}, prev, NOW, mode="featured"))
    assert t["tahoe-featured"].det and not t["tahoe-featured"].ens
    assert not t["tahoe-standard"].det                                           # due, but this mode skips it
    assert all(x.det and x.ens for x in plan(rs, set(), None, NOW))              # nothing published yet


def test_previous_reads_a_directory_and_rejects_other_schemas(tmp_path):
    (tmp_path / "resort").mkdir()
    (tmp_path / "resort" / "a.json").write_text(json.dumps({"schema_version": 2, "x": 1}))
    (tmp_path / "resort" / "old.json").write_text(json.dumps({"schema_version": 1}))
    (tmp_path / "resort" / "broken.json").write_text("{nope")
    prev = Previous(str(tmp_path))
    assert prev.get("resort/a.json") == {"schema_version": 2, "x": 1}
    assert prev.get("resort/old.json") is None                                   # phase-1 files are not reused
    assert prev.get("resort/broken.json") is None and prev.get("resort/missing.json") is None
    got = prev.get_many(["resort/a.json", "resort/missing.json"])
    assert got["resort/a.json"]["x"] == 1 and got["resort/missing.json"] is None
    assert Previous("none").get("resort/a.json") is None and Previous(None).get_many(["x"]) == {"x": None}


def test_age_hours():
    assert age_hours("2026-01-10T08:40:00Z", NOW) == 6.0
    assert age_hours(None, NOW) is None and age_hours("yesterday", NOW) is None
