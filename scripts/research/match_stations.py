"""Match US-West resorts to SNOTEL stations for the phase-3 backtest.

    python scripts/research/match_stations.py

Reads data/resorts.yaml and raw/backtest/snotel_stations.json (AWDB /stations dump),
writes raw/backtest/stations.json: one entry per station that is the best match of at
least one resort.

Grade A: < 5 km and |dz| < 300 m (on the mountain).  Grade B: < 15 km and |dz| < 500 m.
dz is measured against the resort's mid elevation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "backtest"
US_WEST = {"tahoe", "sierra-south", "socal", "utah", "colorado", "southwest", "northern-rockies", "pnw", "alaska"}
FT = 0.3048


def km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def main() -> None:
    resorts = [r for r in yaml.safe_load((ROOT / "data" / "resorts.yaml").read_text())["resorts"] if r["region"] in US_WEST]
    stations = [s for s in json.loads((RAW / "snotel_stations.json").read_text()) if s["networkCode"] == "SNTL"]
    out: dict[str, dict] = {}
    rows = []
    for r in resorts:
        mid = r["elevation_m"]["mid"]
        best = None
        for s in stations:
            d = km(r["lat"], r["lon"], s["latitude"], s["longitude"])
            if d > 15:
                continue
            dz = s["elevation"] * FT - mid
            grade = "A" if d < 5 and abs(dz) < 300 else "B" if abs(dz) < 500 else None
            if grade is None:
                continue
            key = (grade, abs(dz) + 30 * d)          # prefer A, then closest in height and distance
            if best is None or key < best[0]:
                best = (key, s, d, dz, grade)
        if best is None:
            rows.append((r["id"], "-", "", "", ""))
            continue
        _, s, d, dz, grade = best
        t = s["stationTriplet"]
        e = out.setdefault(t, {"triplet": t, "name": s["name"], "lat": s["latitude"], "lon": s["longitude"],
                               "elevation_m": round(s["elevation"] * FT), "region": r["region"], "resorts": []})
        e["resorts"].append({"id": r["id"], "km": round(d, 1), "dz_m": round(dz), "grade": grade})
        rows.append((r["id"], t, s["name"], f"{d:.1f} km", f"{dz:+.0f} m {grade}"))
    for row in rows:
        print("%-28s %-14s %-24s %8s %12s" % row)
    print(f"\n{len(resorts)} resorts, {sum(1 for x in rows if x[1] != '-')} matched, {len(out)} distinct stations")
    (RAW / "stations.json").write_text(json.dumps(sorted(out.values(), key=lambda e: e["triplet"]), indent=1))


if __name__ == "__main__":
    main()
