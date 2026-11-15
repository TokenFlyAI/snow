"""A whole pipeline run with the network replaced by synthetic model data."""
import contextlib
import json
from datetime import datetime, timezone

from pipeline import run as run_mod
from pipeline.verify import archive
from tests.helpers import make_model_data

NOW = datetime(2026, 1, 10, 14, 40, tzinfo=timezone.utc)


def _fake_fetch_model(client, spec, resorts, usage=None):
    out = {}
    for r in resorts:
        md = make_model_data(model=spec.id, n=24 * 12, start="2026-01-09T00", precip_mm_per_h=0.4)
        md.resort_id = r.id
        out[r.id] = md
    return out


def test_run_publishes_and_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "make_client", lambda: contextlib.nullcontext())
    monkeypatch.setattr(run_mod, "fetch_model", _fake_fetch_model)
    monkeypatch.setattr(run_mod, "fetch_ensemble", lambda client, spec, resorts, usage=None: {})
    out, arch = tmp_path / "site", tmp_path / "archive"
    nofeat = tmp_path / "featured.yaml"
    nofeat.write_text("featured: []\n")
    code = run_mod.run(out, only=["alta", "zermatt"], mode="full", previous="none", now=NOW, archive_dir=arch,
                       featured_path=str(nofeat))
    assert code == 0
    assert json.loads((out / "manifest.json").read_text())["resort_count"] == 2
    assert set(json.loads((out / "planner.json").read_text())["resorts"]) == {"alta", "zermatt"}
    rows = list(archive.read_rows(arch))
    assert {r["resort_id"] for r in rows} == {"alta", "zermatt"}
    assert {r["issued_at"] for r in rows} == {"2026-01-10T14:40:00Z"}
    assert (arch / "forecasts" / "2026" / "01" / "10" / "1440Z.jsonl.gz").exists()

    # a run in which nothing is refreshed archives nothing (the fake run fetched no ensembles: stub the cache)
    (out / "ens").mkdir(exist_ok=True)
    (out / "ens" / "zermatt.json").write_text(json.dumps({"schema_version": 2}))
    idx = json.loads((out / "resorts.json").read_text())
    for r in idx["resorts"]:
        r["ensemble_at"] = r["generated_at"]
    (out / "resorts.json").write_text(json.dumps(idx))
    later = datetime(2026, 1, 10, 15, 10, tzinfo=timezone.utc)
    code = run_mod.run(tmp_path / "site2", only=["zermatt"], mode="auto", previous=str(out), now=later,
                       archive_dir=arch, featured_path=str(nofeat))
    assert code == 0 and not (arch / "forecasts" / "2026" / "01" / "10" / "1510Z.jsonl.gz").exists()
