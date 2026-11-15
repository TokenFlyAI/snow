"""trend/{resort_id}.json: how the forecast for each ski day changed over the last issues (design doc B5).

Read from the forecast archive (pipeline/verify/archive.py), so it covers every resort that was
issued at least once in the last TREND_DAYS days, whether or not it was refreshed in this run.

    issues       issue times (oldest first), at most MAX_ISSUES
    days         ski day -> mid-mountain snow (cm) of each issue, aligned with `issues`
                 (null: that issue did not cover the day)

The page shows the change against the newest issue at least 20 hours older ("since yesterday").
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import SCHEMA_VERSION
from ..verify.archive import read_rows

TREND_DAYS = 5
MAX_ISSUES = 12


def _mid(x):
    return x.get("mid") if isinstance(x, dict) else None


def build_trends(archive_dir: Path | str, now: datetime) -> dict[str, dict]:
    today = now.astimezone(timezone.utc).date()
    by: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in read_rows(archive_dir, None, today - timedelta(days=TREND_DAYS), today):
        if row.get("kind") == "point":
            by[row["resort_id"]][row["issued_at"]][row["target_date"]] = _mid(row.get("snow_cm"))
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    first_day = (today - timedelta(days=1)).isoformat()
    out = {}
    for rid, issued in by.items():
        issues = sorted(issued)[-MAX_ISSUES:]
        targets = sorted({d for i in issues for d in issued[i] if d >= first_day})
        out[rid] = {"schema_version": SCHEMA_VERSION, "resort_id": rid, "generated_at": stamp, "units": {"snow": "cm"},
                    "issues": issues,
                    "days": {d: [issued[i].get(d) for i in issues] for d in targets}}
    return out
