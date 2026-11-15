"""Forecast trend per ski day from the archive (pipeline/publish/trend.py)."""
from datetime import datetime, timezone

from pipeline.publish.trend import build_trends
from pipeline.verify import archive

UTC = timezone.utc


def row(rid, issued, day, mid, kind="point"):
    return {"issued_at": issued, "resort_id": rid, "target_date": day, "lead_days": 1, "kind": kind,
            "snow_cm": {"base": mid, "mid": mid, "summit": mid}}


def test_trend_aligns_each_ski_day_with_the_issues(tmp_path):
    t1, t2 = datetime(2026, 12, 9, 2, 40, tzinfo=UTC), datetime(2026, 12, 10, 2, 40, tzinfo=UTC)
    archive._write_gz(archive.path_for(tmp_path, t1), [
        row("alta", "2026-12-09T02:40:00Z", "2026-12-08", 1.0),      # before yesterday: dropped
        row("alta", "2026-12-09T02:40:00Z", "2026-12-11", 10.0),
        row("alta", "2026-12-09T02:40:00Z", "2026-12-21", None, kind="prob")])
    archive._write_gz(archive.path_for(tmp_path, t2), [
        row("alta", "2026-12-10T02:40:00Z", "2026-12-11", 18.0),
        row("alta", "2026-12-10T02:40:00Z", "2026-12-20", 4.0)])
    doc = build_trends(tmp_path, datetime(2026, 12, 10, 8, tzinfo=UTC))["alta"]
    assert doc["issues"] == ["2026-12-09T02:40:00Z", "2026-12-10T02:40:00Z"]
    assert doc["days"] == {"2026-12-11": [10.0, 18.0], "2026-12-20": [None, 4.0]}


def test_no_archive_no_trends(tmp_path):
    assert build_trends(tmp_path, datetime(2026, 12, 10, tzinfo=UTC)) == {}
