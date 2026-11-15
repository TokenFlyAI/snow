"""Pipeline entry point:  python -m pipeline.run --out site/data/v1

    plan -> ingest (Open-Meteo forecast + ensemble APIs) -> derive (elevation
    correction, snow level, SLR) -> blend -> ensemble percentiles -> publish JSON.

Refresh tiers (see config.py and data/featured.yaml):

    featured   every run (6-hourly): all deterministic models
    standard   once a day, in the run before the resort's local morning: 3 models
    ensembles  once a day for every resort (4 ensembles for featured, GEFS otherwise)

Everything that is not due is copied from the previously published data set
(--previous), so each run publishes a complete tree.

Exit code is non-zero when the result is not fit to publish, so the
workflow keeps the previous deployment.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import (API_PER_HOUR, DAILY_DAYS, ENSEMBLES, FORECAST_DAYS, FRESH_WITHIN_H, MODELS, OUTLOOK_WEEKS,
                     PAST_DAYS, STALE_AFTER_H, call_weight, current_slot, ensembles_for, estimate_daily_calls,
                     last_slot_time, load_featured, models_for, refresh_slot)
from .ingest.open_meteo import (ModelData, OpenMeteoError, fetch_model, hourly_vars, make_client, model_weight,
                                profile_vars)
from .ingest.open_meteo_ensemble import EnsembleData, fetch_ensemble
from .process.derive import derive, make_donor
from .process.ensemble import raw_document
from .publish.build import build_index, build_manifest, build_resort, split_daily
from .publish.obs_docs import build_obs_docs
from .publish.planner import build_planner
from .resorts import Resort, load_resorts
from .state import DEFAULT_PREVIOUS, Previous, age_hours, parse_time
from .verify import archive
from .verify.obs import load_stations
from .verify.score import build_verification

log = logging.getLogger("pipeline")
MIN_MODELS_OK = 2
MIN_RESORT_SHARE = 0.9          # publish only if at least this share of the resorts has a document
# One run must fit the hourly API limit: above it the rate limiter waits for the hour to roll over
# and the job times out. After skipped or failed runs every standard resort is due at once
# (5,700 weighted calls with 5 models), so the least overdue ones wait for the next run.
RUN_BUDGET = 0.95 * API_PER_HOUR
ENS_DAYS = 7 * max(OUTLOOK_WEEKS)
STATIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "stations.yaml"


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


@dataclass
class Task:
    resort: Resort
    tier: str
    det: bool      # fetch deterministic models and rebuild the document
    ens: bool      # fetch ensembles
    why: str


def plan(resorts: list[Resort], featured: set[str], prev_index: Optional[dict], now: datetime,
         mode: str = "auto") -> list[Task]:
    """Decide per resort what this run refreshes.

    mode: auto (schedule-driven), full (everything), featured (featured resorts only; whatever
    else is missing from the previous data set is still filled in).
    """
    prev = {r["id"]: r for r in (prev_index or {}).get("resorts", [])}
    tasks = []
    for r in resorts:
        tier = "featured" if r.id in featured else "standard"
        p = prev.get(r.id)
        if mode == "full":
            tasks.append(Task(r, tier, True, True, "full run"))
            continue
        if p is None or p.get("tier") != tier:
            tasks.append(Task(r, tier, True, True, "new" if p is None else "tier changed"))
            continue
        opened = last_slot_time(refresh_slot(r.lon), now)

        def stale(stamp: Optional[str]) -> bool:
            age = age_hours(stamp, now)
            return age is None or age > STALE_AFTER_H

        def due(stamp: Optional[str]) -> bool:
            # made before the slot last opened (also when the slot's own run was skipped or late),
            # but not right after a full run
            t, age = parse_time(stamp), age_hours(stamp, now)
            return mode == "auto" and t is not None and t < opened and age > FRESH_WITHIN_H

        ens = stale(p.get("ensemble_at")) or due(p.get("ensemble_at"))
        det = tier == "featured" or ens or stale(p.get("generated_at")) or due(p.get("generated_at"))
        is_stale = stale(p.get("ensemble_at")) or stale(p.get("generated_at"))
        why = "featured" if tier == "featured" else "carried" if not det else "stale" if is_stale else "due"
        tasks.append(Task(r, tier, det, ens, why))
    return tasks


def task_weight(t: Task) -> float:
    """Weighted Open-Meteo calls this task adds to the run (requests are batched, weight is per location)."""
    w = 0.0
    if t.det:
        w += sum(model_weight(m) for m in models_for(t.resort, t.tier))
    if t.ens:
        w += sum(call_weight(e.members, e.days) for e in ensembles_for(t.tier))
    return w


def cap_to_budget(tasks: list[Task], prev_index: Optional[dict], budget: float) -> int:
    """Defer the least overdue refreshes beyond the budget to the next run. Featured resorts go
    first, then the oldest documents; a resort without a previous document is never deferred.
    Returns the number of deferred resorts."""
    made = {r["id"]: r.get("generated_at") or "" for r in (prev_index or {}).get("resorts", [])}
    todo = sorted((t for t in tasks if t.det or t.ens),
                  key=lambda t: (t.tier != "featured", made.get(t.resort.id, "")))
    used, n = 0.0, 0
    for t in todo:
        w = task_weight(t)
        if used + w <= budget or t.tier == "featured" or not made.get(t.resort.id):
            used += w
            continue
        t.det, t.ens, t.why = False, False, "deferred (run budget)"
        n += 1
    if n:
        log.warning("run budget %.0f weighted calls: %d refreshes deferred to the next run", budget, n)
    return n


def run(out_dir: Path, only: list[str] | None = None, resorts_path: str | None = None,
        mode: str = "auto", previous: Optional[str] = DEFAULT_PREVIOUS, featured_path: str | None = None,
        now: Optional[datetime] = None, archive_dir: Optional[Path] = None,
        stations_path: Optional[str] = None) -> int:
    db = load_resorts(resorts_path) if resorts_path else load_resorts()
    featured = set(load_featured(featured_path) if featured_path else load_featured())
    unknown = featured - {r.id for r in db.resorts}
    if unknown:
        log.error("data/featured.yaml lists unknown resorts: %s", ", ".join(sorted(unknown)))
        return 2
    resorts = [r for r in db.resorts if not only or r.id in only]
    if not resorts:
        log.error("no resorts selected")
        return 2
    now = now or datetime.now(timezone.utc)
    prev = Previous(previous)
    prev_index = prev.get("resorts.json")
    tasks = plan(resorts, featured, prev_index, now, mode)
    n_deferred = cap_to_budget(tasks, prev_index, RUN_BUDGET) if mode == "auto" else 0

    # ---- previously published files for everything that is not refreshed ----------------
    carried = prev.get_many(f"resort/{t.resort.id}.json" for t in tasks if not t.det)
    old_ens = prev.get_many(f"ens/{t.resort.id}.json" for t in tasks if not t.ens)
    for t in tasks:
        if not t.det and carried.get(f"resort/{t.resort.id}.json") is None:
            t.det, t.why = True, "previous document unavailable"
        if not t.ens and old_ens.get(f"ens/{t.resort.id}.json") is None:
            t.ens, t.det, t.why = True, True, "previous ensemble unavailable"
    det_tasks = [t for t in tasks if t.det]
    ens_tasks = [t for t in tasks if t.ens]
    log.info("%d resorts (%d featured): deterministic refresh %d, ensemble refresh %d, carried over %d  [mode=%s, slot=%02d UTC]",
             len(tasks), sum(t.tier == "featured" for t in tasks), len(det_tasks), len(ens_tasks),
             len(tasks) - len(det_tasks), mode, current_slot(now.hour))

    usage: dict = {}
    raw: dict[str, dict[str, ModelData]] = {}
    status: dict[str, dict] = {}
    ens_data: dict[str, dict[str, EnsembleData]] = {}
    ens_status: dict[str, dict] = {}

    with make_client() as client:
        for spec in MODELS:
            wanted = [t.resort for t in det_tasks if spec in models_for(t.resort, t.tier)]
            if not wanted:
                continue
            try:
                raw[spec.id] = fetch_model(client, spec, wanted, usage=usage)
                n_ok = sum(1 for md in raw[spec.id].values() if md.has_data)
                status[spec.id] = {"label": spec.label, "kind": spec.kind,
                                   "status": "ok" if n_ok else "missing",
                                   "resorts_ok": n_ok, "resorts_requested": len(wanted)}
                log.info("%-28s ok for %d/%d resorts", spec.id, n_ok, len(wanted))
            except OpenMeteoError as e:
                status[spec.id] = {"label": spec.label, "kind": spec.kind, "status": "missing",
                                   "resorts_ok": 0, "resorts_requested": len(wanted), "error": str(e)[:200]}
                log.warning("%-28s dropped: %s", spec.id, e)
        for spec in ENSEMBLES:
            wanted = [t.resort for t in ens_tasks if spec in ensembles_for(t.tier)]
            if not wanted:
                continue
            try:
                ens_data[spec.id] = fetch_ensemble(client, spec, wanted, usage=usage)
                n_ok = sum(1 for ed in ens_data[spec.id].values() if ed.has_data)
                ens_status[spec.id] = {"label": spec.label, "members": spec.members, "days": spec.days,
                                       "status": "ok" if n_ok else "missing",
                                       "resorts_ok": n_ok, "resorts_requested": len(wanted)}
                log.info("ensemble %-19s ok for %d/%d resorts", spec.id, n_ok, len(wanted))
            except OpenMeteoError as e:
                ens_status[spec.id] = {"label": spec.label, "members": spec.members, "days": spec.days,
                                       "status": "missing", "resorts_ok": 0, "resorts_requested": len(wanted),
                                       "error": str(e)[:200]}
                log.warning("ensemble %-19s dropped: %s", spec.id, e)

    n_models_ok = sum(1 for s in status.values() if s["status"] == "ok")
    if det_tasks and n_models_ok < MIN_MODELS_OK:
        log.error("only %d models available (< %d): not publishing", n_models_ok, MIN_MODELS_OK)
        return 1

    docs, failed, n_carried = [], [], 0
    issued: list[dict] = []          # documents built in this run (for the forecast archive)
    for t in tasks:
        resort = t.resort
        # ---- ensemble member totals: fresh, or the cached file from the last refresh ----
        ens_raw = old_ens.get(f"ens/{resort.id}.json")
        if t.ens:
            got = {mid: (d[resort.id].time, d[resort.id].members) for mid, d in ens_data.items()
                   if resort.id in d and d[resort.id].has_data}
            if got:
                from zoneinfo import ZoneInfo
                today = now.astimezone(ZoneInfo(resort.timezone)).date()
                ens_raw = raw_document(resort.id, resort.elevation_m.mid, today, ENS_DAYS, resort.timezone, got, now)
            else:
                ens_raw = prev.get(f"ens/{resort.id}.json")   # keep yesterday's rather than nothing
        if ens_raw:
            _write(out_dir / "ens" / f"{resort.id}.json", ens_raw)

        # ---- resort document ----
        doc = None
        if t.det:
            expected = [m.id for m in models_for(resort, t.tier)]
            mds = [raw[m][resort.id] for m in expected if m in raw and resort.id in raw[m] and raw[m][resort.id].has_data]
            missing = [m for m in expected if m not in {md.model for md in mds}]
            if mds:
                first = [derive(md, resort) for md in mds]
                donor = make_donor(first)
                derived = [d if d.has_profile else derive(md, resort, donor) for d, md in zip(first, mds)]
                doc = build_resort(resort, derived, now, missing_models=missing, ens_raw=ens_raw, tier=t.tier)
                issued.append(doc)
                s = doc["summary"]
                log.debug("%-26s %-8s models=%d members=%d  24h=%s 72h=%s 7d=%s 16d=%s cm (mid)", resort.id, t.tier,
                          len(derived), sum(m["members"] for m in (doc["ensemble"] or {}).get("models", [])),
                          s["snow_24h_cm"]["mid"], s["snow_72h_cm"]["mid"], s["snow_7d_cm"]["mid"], s["snow_16d_cm"]["mid"])
            else:
                doc = prev.get(f"resort/{resort.id}.json")    # keep the old forecast rather than drop the resort
                if doc:
                    log.warning("%s: no model data, keeping the previous document", resort.id)
        else:
            doc = carried[f"resort/{resort.id}.json"]
            n_carried += 1
        if doc is None:
            failed.append(resort.id)
            continue
        split_daily(doc)
        _write(out_dir / "resort" / f"{resort.id}.json", doc)
        docs.append(doc)

    if failed:
        log.warning("no data for %d resorts: %s", len(failed), ", ".join(failed))
    if len(docs) < MIN_RESORT_SHARE * len(tasks):
        log.error("only %d of %d resorts have a forecast: not publishing", len(docs), len(tasks))
        return 1

    budget = estimate_daily_calls(db.resorts, featured, len(hourly_vars()), len(profile_vars()))
    run_info = {
        "mode": mode, "slot_utc": current_slot(now.hour),
        "resorts": len(tasks), "featured": sum(t.tier == "featured" for t in tasks),
        "refreshed_deterministic": len(det_tasks), "refreshed_ensemble": len(ens_tasks),
        "carried_over": n_carried, "failed": failed, "deferred": n_deferred,
    }
    if archive_dir is not None:
        try:
            path = archive.write_run(archive_dir, issued, now)
            log.info("archived %d issued forecasts -> %s", len(issued), path)
        except Exception as e:  # noqa: BLE001  the archive must never stop a publish
            log.warning("forecast archive not written: %s", e)
    if stations_path:
        run_info["obs"] = publish_obs(out_dir, resorts, load_stations(stations_path), now, prev,
                                      archive_dir=archive_dir)
    if archive_dir is not None:
        run_info["verification"] = publish_verification(out_dir, archive_dir, db.resorts, now, prev)
    _write(out_dir / "resorts.json", build_index(db.regions, docs, now))
    _write(out_dir / "planner.json", build_planner(db.regions, docs, now))
    # manifest is written last: its presence marks a complete run
    _write(out_dir / "manifest.json", build_manifest(now, status, len(docs), usage, ens_status, run_info, budget))
    log.info("published %d resorts (%d refreshed, %d carried over); this run ~%.0f weighted API calls %s; "
             "scheduled daily total ~%.0f of %d -> %s", len(docs), len(det_tasks), n_carried,
             usage.get("weighted_calls", 0.0), {k: round(v) for k, v in usage.get("by_kind", {}).items()},
             budget["total"], 10000, out_dir)
    return 0


def publish_obs(out_dir: Path, resorts: list[Resort], stations: dict[str, list[dict]], now: datetime,
                prev: Previous, fetch=None, archive_dir: Optional[Path] = None) -> dict:
    """obs/{id}.json for resorts with stations; on failure the previous files are kept. Never fails the run.
    With archive_dir the completed observed days also go to the archive (for scoring)."""
    wanted = [r for r in resorts if stations.get(r.id)]
    try:
        docs = build_obs_docs(wanted, stations, now, fetch)
        status = "ok"
    except Exception as e:  # noqa: BLE001  observations are an extra: never stop a publish
        log.warning("observations not refreshed (%s): keeping the previous files", e)
        docs, status = {}, "previous"
    if archive_dir is not None and docs:
        try:
            archive.write_obs(archive_dir, docs.values())
        except Exception as e:  # noqa: BLE001
            log.warning("observations not archived: %s", e)
    missing = [r.id for r in wanted if r.id not in docs]
    for rid, d in prev.get_many(f"obs/{rid}.json" for rid in missing).items():
        if d:
            docs[d["resort_id"]] = d
    for rid, d in docs.items():
        _write(out_dir / "obs" / f"{rid}.json", d)
    return {"status": status, "resorts": len(docs), "resorts_with_stations": len(wanted)}


def publish_verification(out_dir: Path, archive_dir: Path, resorts: list[Resort], now: datetime,
                         prev: Previous) -> dict:
    """verification.json from the archive (A3); on failure the previous file is kept. Never fails the run."""
    try:
        doc = build_verification(archive_dir, {r.id: r.region for r in resorts}, now)
        status = "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("verification not computed (%s): keeping the previous file", e)
        doc, status = prev.get("verification.json"), "previous"
    if doc:
        _write(out_dir / "verification.json", doc)
        season = doc["windows"]["season"]
        log.info("verification: %d resorts, %d ski days scored this season", season["resorts"], season["ski_days"])
        return {"status": status, "season_ski_days": season["ski_days"], "season_resorts": season["resorts"]}
    return {"status": "none"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="site/data/v1", help="output directory")
    ap.add_argument("--resorts", default="", help="comma-separated resort ids (default: all)")
    ap.add_argument("--resorts-file", default=None)
    ap.add_argument("--featured-file", default=None)
    ap.add_argument("--mode", choices=("auto", "full", "featured"), default="auto",
                    help="auto: follow the refresh schedule (default); full: refresh everything; "
                         "featured: only the featured resorts")
    ap.add_argument("--previous", default=os.environ.get("SNOW_PREVIOUS", DEFAULT_PREVIOUS),
                    help="URL or directory of the last published data set, or 'none'")
    ap.add_argument("--archive", default=os.environ.get("SNOW_ARCHIVE") or None,
                    help="also write this run's issued forecasts to DIR/forecasts/... (see pipeline/verify/archive.py)")
    ap.add_argument("--stations", default=os.environ.get("SNOW_STATIONS", str(STATIONS_FILE)),
                    help="station list for observations (data/stations.yaml), or 'none'")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    only = [s.strip() for s in args.resorts.split(",") if s.strip()] or None
    return run(Path(args.out), only, args.resorts_file, args.mode, args.previous, args.featured_file,
               archive_dir=Path(args.archive) if args.archive else None,
               stations_path=None if args.stations == "none" else args.stations)


if __name__ == "__main__":
    sys.exit(main())
