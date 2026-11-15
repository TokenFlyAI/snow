"""Calendar feeds of powder days (pipeline/publish/ics.py)."""
from datetime import datetime, timezone

from pipeline.publish.ics import areas, calendar, esc, fold, powder_days, write_feeds
from pipeline.publish.planner import POINT_FIELDS, PROB_FIELDS

UTC = timezone.utc
NOW = datetime(2026, 1, 9, 18, 0, tzinfo=UTC)          # 10:00 in Tahoe, 19:00 in the Alps


def day(date, score, p15, fresh=25.0, **kw):
    d = {"date": date, "lead": 0, "score": score, "fresh": fresh, "night": fresh, "cm": fresh, "low": 10.0,
         "high": 40.0, "p2_5": 0.95, "p15": p15, "quality": "powder", "gust": 40.0, "rain": 0.0, "rain_mid": 0,
         "conf": "high"}
    d.update(kw)
    return [d[f] for f in POINT_FIELDS]


def planner():
    meta = lambda name, region, tz, passes: {"name": name, "name_zh": None, "destination": None, "region": region,  # noqa: E731
                                             "country": "US", "state": None, "lat": 39.0, "lon": -120.0, "timezone": tz,
                                             "tier": "featured", "passes": passes, "mid_m": 2000, "prob_days": []}
    return {"fields": list(POINT_FIELDS), "prob_fields": list(PROB_FIELDS),
            "regions": [{"id": "tahoe", "name": "Lake Tahoe", "name_zh": "太浩湖"},
                        {"id": "alps-fr", "name": "French Alps", "name_zh": "法国阿尔卑斯"}],
            "resorts": {
                "kirkwood": meta("Kirkwood", "tahoe", "America/Los_Angeles", {"epic": "unlimited"}) | {"days": [
                    day("2026-01-09", 120, 0.9),               # today, lifts open: listed
                    day("2026-01-10", 59, 0.9),                # score too low
                    day("2026-01-11", 80, 0.55),               # probability too low
                    day("2026-01-13", 90, 0.8),                # 4 days ahead: listed
                    day("2026-01-14", 150, 0.9)]},             # 5 days ahead: not
                "tignes": meta("Tignes", "alps-fr", "Europe/Paris", {"ikon": "7-day"}) | {"days": [
                    day("2026-01-09", 100, 0.9),               # 19:00 in Tignes: lifts closed, skipped
                    day("2026-01-10", 70, 0.7, gust=110.0)]},
            }}


def test_which_days_become_events():
    got = [(rid, d["date"]) for rid, _, d in powder_days(planner(), NOW)]
    assert got == [("kirkwood", "2026-01-09"), ("tignes", "2026-01-10"), ("kirkwood", "2026-01-13")]


def test_feeds_per_language_pass_and_area(tmp_path):
    groups = [{"id": "us-west", "name": "US West", "name_zh": "美国西部", "regions": ["tahoe", "utah"]}]
    assert set(areas(["tahoe", "alps-fr"], groups)) == {"all", "g-us-west", "tahoe", "alps-fr"}
    n = write_feeds(tmp_path, planner(), NOW, groups)
    assert n == 2 * 3 * 4
    epic_west = (tmp_path / "ics/en/epic/g-us-west.ics").read_text()
    assert epic_west.count("BEGIN:VEVENT") == 2 and "Kirkwood" in epic_west and "Tignes" not in epic_west
    assert "BEGIN:VEVENT" not in (tmp_path / "ics/en/ikon/tahoe.ics").read_text()      # empty feeds still exist
    zh = (tmp_path / "ics/zh/ikon/alps-fr.ics").read_text()
    assert "粉雪日 · Ikon · 法国阿尔卑斯" in zh and "缆车可能停" in zh


def test_icalendar_format():
    evs = powder_days(planner(), NOW)
    text = calendar("en", "Powder days · Epic · US West", evs, NOW)
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and lines[-1] == ""
    assert all(len(x.encode("utf-8")) <= 75 for x in lines)
    assert "\n" not in text.replace("\r\n", "")
    assert "UID:kirkwood-2026-01-09@snow.tokenfly.ai" in text
    assert "DTSTART;VALUE=DATE:20260109" in text and "DTEND;VALUE=DATE:20260110" in text
    assert "SUMMARY:Powder day: Kirkwood\\, 10″ fresh" in text


def test_folding_and_escaping():
    s = "DESCRIPTION:" + "新雪, 粉雪; " * 20
    folded = fold(esc(s))
    assert all(len(x.encode("utf-8")) <= 75 for x in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == esc(s)                    # unfolding gives the line back
    assert esc("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"
