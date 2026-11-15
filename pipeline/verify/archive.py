"""Forecast archive: every forecast we issue, kept so it can be scored later (design doc A2).

Each pipeline run writes one file with a row per (refreshed resort, ski day):

    forecasts/YYYY/MM/DD/HHMMZ.jsonl.gz        (UTC time of the run)

Only resorts whose document was rebuilt in that run are written, so a forecast appears once, at the
time it was issued. The forecast workflow commits these files to the orphan branch `archive` of this
repository; publishing never depends on it.

A row (all values in the published units: cm, mm, degC, m, km/h):

    issued_at      when the forecast was made (the document's generated_at)
    ensemble_at    when its ensemble members were fetched (null: no ensemble)
    resort_id, tier, method ("v2": the phase-2 blend, frozen as the baseline)
    target_date    the ski day: 16:00 the day before -> 16:00 that day, resort local time
    lead_days      0 = today's ski day in the resort's time zone when the forecast was made
    kind           "point" (lead 0-9: blended value) or "prob" (lead 10-15: ensemble only)
    point rows:    snow_cm, snow_night_cm, snow_low_cm, snow_high_cm   {base, mid, summit}
                   precip_mm, rain_base_mm, slr, quality, snow_level_m {min, max}, freezing_level_m,
                   temp_max_c / temp_min_c {base, summit}, gust_max_kmh, wind_avg_kmh,
                   confidence, range_source, n_models, by_model {model id: mid-mountain snow cm}
    both:          ens  {p10, p50, p90, mean, p_2_5, p_15, n_members, agreement}  (mid-mountain), or null
                   ens_factor  the ensemble calibration factor of that document
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

METHOD = "v2"
POINT_FIELDS = ("snow_cm", "snow_night_cm", "snow_low_cm", "snow_high_cm", "precip_mm", "rain_base_mm", "slr",
                "quality", "snow_level_m", "freezing_level_m", "temp_max_c", "temp_min_c", "gust_max_kmh",
                "wind_avg_kmh", "confidence", "range_source", "n_models")

README = """# Forecast archive

Every forecast published at https://tokenfly.ai/snow/, written by the `forecast` workflow of the main
branch. `forecasts/YYYY/MM/DD/HHMMZ.jsonl.gz` holds one JSON row per (resort, ski day) for the resorts
refreshed in that run. The row format is documented in `pipeline/verify/archive.py` on `main`; read it
back with `pipeline.verify.archive.read_rows`.
"""


def _ens(e: Optional[dict]) -> Optional[dict]:
    if not e:
        return None
    mid = lambda key: (e.get(key) or {}).get("mid")  # noqa: E731
    prob = e.get("prob") or {}
    return {"p10": mid("p10"), "p50": mid("p50"), "p90": mid("p90"), "mean": mid("mean"),
            "p_2_5": (prob.get("2.5") or {}).get("mid"), "p_15": (prob.get("15") or {}).get("mid"),
            "n_members": e.get("n_members"), "agreement": e.get("agreement")}


def rows_from_doc(doc: dict) -> list[dict]:
    """Archive rows of one published resort document."""
    meta = doc["resort"]
    ensemble = doc.get("ensemble") or {}
    head = {"issued_at": doc["generated_at"], "ensemble_at": ensemble.get("generated_at"),
            "resort_id": meta["id"], "tier": meta.get("tier"), "method": METHOD}
    factor = (ensemble.get("calibration") or {}).get("factor")
    by_model = doc.get("by_model_daily_cm") or {}
    rows = []
    for e in doc.get("daily", []):
        k = e["lead_days"]
        row = {**head, "target_date": e["date"], "lead_days": k, "kind": "point"}
        row.update({f: e.get(f) for f in POINT_FIELDS})
        row["by_model"] = {m: (v.get("mid") or [])[k] if k < len(v.get("mid") or []) else None
                           for m, v in by_model.items()}
        row["ens"], row["ens_factor"] = _ens(e.get("ens")), factor
        rows.append(row)
    for e in doc.get("daily_prob", []):
        rows.append({**head, "target_date": e["date"], "lead_days": e["lead_days"], "kind": "prob",
                     "ens": _ens(e.get("ens")), "ens_factor": factor})
    return rows


def path_for(root: Path, issued: datetime) -> Path:
    t = issued.astimezone(timezone.utc)
    return Path(root) / "forecasts" / f"{t:%Y}" / f"{t:%m}" / f"{t:%d}" / f"{t:%H%M}Z.jsonl.gz"


def write_run(root: Path | str, docs: Iterable[dict], issued: datetime) -> Optional[Path]:
    """Write the rows of this run's refreshed documents. Returns the file, or None when there is nothing."""
    rows = [row for d in docs for row in rows_from_doc(d)]
    if not rows:
        return None
    root = Path(root)
    path = path_for(root, issued)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n" for r in rows)
    # mtime=0: the same rows always give the same bytes
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(body.encode("utf-8"))
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    return path


def read_rows(root: Path | str, resort_ids: Optional[Iterable[str]] = None,
              start: Optional[date] = None, end: Optional[date] = None) -> Iterator[dict]:
    """Rows of the forecasts issued between `start` and `end` (UTC dates, inclusive), oldest first."""
    want = set(resort_ids) if resort_ids else None
    for f in sorted((Path(root) / "forecasts").glob("*/*/*/*.jsonl.gz")):
        y, m, d = (int(x) for x in f.parts[-4:-1])
        day = date(y, m, d)
        if (start and day < start) or (end and day > end):
            continue
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                if want is None or row["resort_id"] in want:
                    yield row
