"""Pipeline entry point:  python -m pipeline.run --out site/data/v1

ingest (Open-Meteo, one request per model) -> derive (elevation correction,
snow level, SLR) -> blend -> aggregate -> publish static JSON.

Exit code is non-zero when the result is not fit to publish, so the
workflow keeps the previous deployment.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import MODEL_BY_ID, MODELS, models_for
from .ingest.open_meteo import ModelData, OpenMeteoError, fetch_model, make_client
from .process.derive import derive, make_donor
from .publish.build import build_index, build_manifest, build_resort
from .resorts import load_resorts

log = logging.getLogger("pipeline")
MIN_MODELS_OK = 2


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def run(out_dir: Path, only: list[str] | None = None, resorts_path: str | None = None) -> int:
    db = load_resorts(resorts_path) if resorts_path else load_resorts()
    resorts = [r for r in db.resorts if not only or r.id in only]
    if not resorts:
        log.error("no resorts selected")
        return 2
    now = datetime.now(timezone.utc)
    usage: dict = {}
    raw: dict[str, dict[str, ModelData]] = {}
    status: dict[str, dict] = {}

    with make_client() as client:
        for spec in MODELS:
            wanted = [r for r in resorts if spec in models_for(r)]
            if not wanted:
                continue
            try:
                raw[spec.id] = fetch_model(client, spec, wanted, usage=usage)
                n_ok = sum(1 for md in raw[spec.id].values() if md.has_data)
                status[spec.id] = {"label": spec.label, "kind": spec.kind,
                                   "status": "ok" if n_ok else "missing",
                                   "resorts_ok": n_ok, "resorts_requested": len(wanted)}
                log.info("%-22s ok for %d/%d resorts", spec.id, n_ok, len(wanted))
            except OpenMeteoError as e:
                status[spec.id] = {"label": spec.label, "kind": spec.kind, "status": "missing",
                                   "resorts_ok": 0, "resorts_requested": len(wanted), "error": str(e)[:200]}
                log.warning("%-22s dropped: %s", spec.id, e)

    n_models_ok = sum(1 for s in status.values() if s["status"] == "ok")
    if n_models_ok < MIN_MODELS_OK:
        log.error("only %d models available (< %d): not publishing", n_models_ok, MIN_MODELS_OK)
        return 1

    docs, failed = [], []
    for resort in resorts:
        expected = [m.id for m in models_for(resort)]
        mds = [raw[m][resort.id] for m in expected if m in raw and resort.id in raw[m] and raw[m][resort.id].has_data]
        missing = [m for m in expected if m not in {md.model for md in mds}]
        if not mds:
            failed.append(resort.id)
            continue
        first = [derive(md, resort) for md in mds]
        donor = make_donor(first)
        derived = [d if d.has_profile else derive(md, resort, donor) for d, md in zip(first, mds)]
        doc = build_resort(resort, derived, now, missing_models=missing)
        _write(out_dir / "resort" / f"{resort.id}.json", doc)
        docs.append(doc)
        s = doc["summary"]
        log.info("%-20s models=%d  24h=%s  72h=%s  7d=%s  16d=%s cm (mid)", resort.id, len(derived),
                 s["snow_24h_cm"]["mid"], s["snow_72h_cm"]["mid"], s["snow_7d_cm"]["mid"], s["snow_16d_cm"]["mid"])

    if failed:
        log.error("no data at all for: %s: not publishing", ", ".join(failed))
        return 1

    _write(out_dir / "resorts.json", build_index(db.regions, docs, now))
    # manifest is written last: its presence marks a complete run
    _write(out_dir / "manifest.json", build_manifest(now, status, len(docs), usage))
    log.info("published %d resorts, %d models, ~%.0f weighted API calls -> %s",
             len(docs), n_models_ok, usage.get("weighted_calls", 0.0), out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="site/data/v1", help="output directory")
    ap.add_argument("--resorts", default="", help="comma-separated resort ids (default: all)")
    ap.add_argument("--resorts-file", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    only = [s.strip() for s in args.resorts.split(",") if s.strip()] or None
    return run(Path(args.out), only, args.resorts_file)


if __name__ == "__main__":
    sys.exit(main())
