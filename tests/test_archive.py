"""The forecast archive (design doc A2): rows written per run, read back by resort and date."""
import gzip
import json
from datetime import date, datetime, timezone

from pipeline.process.derive import derive
from pipeline.publish.build import build_resort
from pipeline.verify import archive
from tests.helpers import make_resort
from tests.test_derive_build import NOW, _ens_raw, _mds


def _doc(resort_id="test-mountain"):
    r = make_resort(id=resort_id)
    return build_resort(r, [derive(m, r) for m in _mds()], NOW, ens_raw=_ens_raw(), tier="featured")


def test_rows_cover_point_and_probability_days():
    doc = _doc()
    rows = archive.rows_from_doc(doc)
    assert [r["kind"] for r in rows] == ["point"] * 10 + ["prob"] * 6
    assert [r["lead_days"] for r in rows] == list(range(16))
    p, q = rows[3], rows[12]
    assert p["issued_at"] == doc["generated_at"] and p["method"] == "v2" and p["tier"] == "featured"
    assert p["target_date"] == doc["daily"][3]["date"] and p["snow_cm"] == doc["daily"][3]["snow_cm"]
    assert set(p["by_model"]) == {m["id"] for m in doc["models"] if m["status"] == "ok"}
    assert p["by_model"]["gfs_global"] == doc["by_model_daily_cm"]["gfs_global"]["mid"][3]
    assert p["ens"]["p10"] <= p["ens"]["p50"] <= p["ens"]["p90"] and 0 <= p["ens"]["p_15"] <= p["ens"]["p_2_5"] <= 1
    assert "snow_cm" not in q and q["ens"]["n_members"] == 20
    json.dumps(rows, allow_nan=False)


def test_write_and_read_back(tmp_path):
    issued = datetime(2026, 1, 10, 14, 41, tzinfo=timezone.utc)
    path = archive.write_run(tmp_path, [_doc("a"), _doc("b")], issued)
    assert path == tmp_path / "forecasts" / "2026" / "01" / "10" / "1441Z.jsonl.gz"
    assert (tmp_path / "README.md").exists()
    first = path.read_bytes()
    archive.write_run(tmp_path, [_doc("a"), _doc("b")], issued)
    assert path.read_bytes() == first                          # same rows, same bytes (no timestamp in the gzip)
    with gzip.open(path, "rt") as f:
        assert sum(1 for _ in f) == 32
    archive.write_run(tmp_path, [_doc("a")], datetime(2026, 1, 12, 2, 40, tzinfo=timezone.utc))
    assert len(list(archive.read_rows(tmp_path))) == 48
    assert {r["resort_id"] for r in archive.read_rows(tmp_path, ["b"])} == {"b"}
    assert len(list(archive.read_rows(tmp_path, start=date(2026, 1, 11)))) == 16
    assert len(list(archive.read_rows(tmp_path, end=date(2026, 1, 10)))) == 32


def test_nothing_issued_writes_nothing(tmp_path):
    assert archive.write_run(tmp_path, [], NOW) is None
    assert not (tmp_path / "forecasts").exists()
