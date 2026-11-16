"""Drive times from the cities in data/cities.yaml to every resort: writes data/drive.json.

    python scripts/build_drive_table.py              # all cities (~15 min: one request a second)
    python scripts/build_drive_table.py denver       # one city, printed; nothing written

Road distance comes from the public OSRM server (OpenStreetMap road network). The time is our own
conversion of that distance, calibrated on 22 routes with known drive times:

    minutes = 10 + road_km / 94 km/h       mean error 17 min, worst 47 min (slow mountain roads)

OSRM's own durations did worse (mean error 19 min; on this server motorways come out up to 70 %
too slow), and a straight-line estimate was off by an hour in the median.

Winter: a route within radius_km of a pass in data/winter_closures.yaml is replaced by the
shortest route through one of that pass's detour points that avoids every closure; the pass ids
go to "via". Pass roads run over the summit point, so the radius is small (0.5 km; 0.2 km where a
tunnel runs under the pass). Routes that come within 2 km are printed for a look.
Car trains (Loetschberg, Furka, Vereina: OSRM calls them ferries) are allowed and cost
TRAIN_MIN extra; a route with any other ferry is dropped.
Responses are cached under .cache/osrm, so a rerun after an error only asks for what is missing.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
OSRM = "https://router.project-osrm.org"
CACHE = ROOT / ".cache" / "osrm"
OUT = ROOT / "data" / "drive.json"

MAX_GC_KM = 700          # resorts further than this in a straight line are never within MAX_MINUTES
MAX_MINUTES = 9 * 60
BASE_MIN = 10.0
SPEED_KMH = 94.0
FERRY_SUSPECT = 2.0      # OSRM duration this many times our estimate: look at the route for a ferry
CLOSURE_RADIUS_KM = 0.5
NEAR_KM = 2.0
TRAIN_MIN = 20           # loading and waiting for a car train
CAR_TRAIN = re.compile(r"autoverlad|autozug|car train|vereina", re.I)
# Regions with islands, where a ferry is not always much slower than driving (Hokkaido - Honshu):
# every route to them is looked at step by step.
FERRY_REGIONS = {"japan", "new-zealand", "east-asia"}


def minutes(road_km: float, trains: int = 0) -> int:
    return round(BASE_MIN + road_km / SPEED_KMH * 60 + TRAIN_MIN * trains)


def gc_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def _seg_km(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from p to segment a-b (lat, lon), flat-earth around p: fine for a few km."""
    kx = 111.32 * math.cos(math.radians(p[0]))
    ax, ay, bx, by = (a[1] - p[1]) * kx, (a[0] - p[0]) * 110.57, (b[1] - p[1]) * kx, (b[0] - p[0]) * 110.57
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    return math.hypot(ax + t * dx, ay + t * dy)


def min_km(path: list[tuple[float, float]], point: tuple[float, float], within: float = NEAR_KM) -> float:
    """Closest approach of the polyline to point (km); inf if not within `within`."""
    if len(path) == 1:
        d = gc_km(path[0], point)
        return d if d <= within else math.inf
    pad = within / 100.0 + 0.01
    best = math.inf
    for a, b in zip(path, path[1:]):
        if min(a[0], b[0]) - pad > point[0] or max(a[0], b[0]) + pad < point[0]:
            continue
        best = min(best, _seg_km(point, a, b))
    return best if best <= within else math.inf


def maybe_on_route(stops: list[tuple[float, float]], road_km: float, c: dict, slack_km: float = 3.0) -> bool:
    """Could a route of road_km through these stops go over closure c? (Going over it makes the road
    at least as long as the straight lines through it.)"""
    p = (c["lat"], c["lon"])
    legs = [gc_km(a, b) for a, b in zip(stops, stops[1:])]
    best = min(sum(legs) - legs[i] + gc_km(stops[i], p) + gc_km(p, stops[i + 1]) for i in range(len(legs)))
    return best <= road_km + slack_km


def closures_on(path, stops, road_km, closures: Iterable[dict], near: Optional[list] = None) -> list[str]:
    """Closures the route goes over; near misses (within NEAR_KM) are appended to `near`."""
    out = []
    for c in closures:
        if not maybe_on_route(stops, road_km, c):
            continue
        d = min_km(path, (c["lat"], c["lon"]))
        if d <= c.get("radius_km", CLOSURE_RADIUS_KM):
            out.append(c["id"])
        elif d < math.inf and near is not None:
            near.append((c["id"], round(d, 2)))
    return out


# ---- OSRM ----------------------------------------------------------------------------------------

class Osrm:
    def __init__(self, cache: Path = CACHE, pause_s: float = 1.1):
        self.cache, self.pause_s, self.last = cache, pause_s, 0.0
        self.client = httpx.Client(timeout=90, headers={"User-Agent": "drive-table-builder/1.0"})
        self.requests = 0

    def get(self, path: str) -> dict:
        key = self.cache / (hashlib.sha1(path.encode()).hexdigest() + ".json")
        if key.exists():
            return json.loads(key.read_text())
        for attempt in range(5):
            wait = self.last + self.pause_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.requests += 1
            try:
                r = self.client.get(OSRM + path)
            except httpx.TransportError:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(10 * (attempt + 1))
                continue
            d = r.json()
            if d.get("code") != "Ok" and d.get("code") not in ("NoRoute", "NoSegment"):
                raise RuntimeError(f"OSRM {d.get('code')}: {d.get('message')} for {path[:120]}")
            key.parent.mkdir(parents=True, exist_ok=True)
            key.write_text(json.dumps(d))
            return d
        raise RuntimeError(f"OSRM unreachable for {path[:120]}")

    @staticmethod
    def _coords(points) -> str:
        return ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)

    def table(self, src: tuple[float, float], dests: list[tuple[float, float]]) -> list[tuple[Optional[float], Optional[float]]]:
        """(road km, OSRM minutes) from src to each destination; (None, None) if unreachable."""
        d = self.get(f"/table/v1/driving/{self._coords([src, *dests])}?sources=0&annotations=distance,duration")
        if d.get("code") != "Ok":
            return [(None, None)] * len(dests)
        dist, dur = d["distances"][0][1:], d["durations"][0][1:]
        return [(None, None) if a is None else (a / 1000, b / 60) for a, b in zip(dist, dur)]

    def route(self, stops: list[tuple[float, float]]) -> Optional[dict]:
        d = self.get(f"/route/v1/driving/{self._coords(stops)}?overview=full&geometries=geojson&steps=true")
        if d.get("code") != "Ok" or not d.get("routes"):
            return None
        rt = d["routes"][0]
        boats = [s.get("name") or "" for leg in rt["legs"] for s in leg["steps"] if s["mode"] == "ferry"]
        trains = sum(1 for b in dict.fromkeys(boats) if CAR_TRAIN.search(b))
        return {"km": rt["distance"] / 1000, "path": [(lat, lon) for lon, lat in rt["geometry"]["coordinates"]],
                "ferry": any(not CAR_TRAIN.search(b) for b in boats), "trains": trains}


# ---- the table -----------------------------------------------------------------------------------

def load():
    cities = yaml.safe_load((ROOT / "data" / "cities.yaml").read_text())["cities"]
    resorts = yaml.safe_load((ROOT / "data" / "resorts.yaml").read_text())["resorts"]
    cl = yaml.safe_load((ROOT / "data" / "winter_closures.yaml").read_text())
    targets = yaml.safe_load((ROOT / "data" / "drive_targets.yaml").read_text()) or {}
    for r in resorts:                       # drive to the base area where the terrain centre snaps badly
        if r["id"] in targets:
            r["lat"], r["lon"] = targets[r["id"]]
    return cities, resorts, cl["closures"], {k: tuple(v) for k, v in cl["detours"].items()}


def drive(osrm: Osrm, city: dict, resorts: list[dict], closures: list[dict], detours: dict, log=print) -> dict:
    """resort id -> {"min": minutes, "km": road km, "via": [closure ids]} for one city."""
    src = (city["lat"], city["lon"])
    near = [r for r in resorts if gc_km(src, (r["lat"], r["lon"])) <= MAX_GC_KM]
    if not near:
        return {}
    out = {}
    for r, (km, osrm_min) in zip(near, osrm.table(src, [(x["lat"], x["lon"]) for x in near])):
        if km is None:
            continue
        dst = (r["lat"], r["lon"])
        cand = [c for c in closures if maybe_on_route([src, dst], km, c)]
        if not cand and osrm_min <= FERRY_SUSPECT * minutes(km) and r["region"] not in FERRY_REGIONS:
            if minutes(km) <= MAX_MINUTES:
                out[r["id"]] = {"min": minutes(km), "km": round(km)}
            continue
        rt = osrm.route([src, dst])
        if rt is None:
            continue
        tag = f"  {city['id']} -> {r['id']}:"
        if rt["ferry"]:
            log(f"{tag} ferry, dropped")
            continue
        near_miss: list = []
        used = closures_on(rt["path"], [src, dst], rt["km"], cand, near_miss)
        if near_miss and minutes(rt["km"]) <= MAX_MINUTES:
            log(f"{tag} passes near {near_miss} (km), counted as open")
        if not used:
            m = minutes(rt["km"], rt["trains"])
            if m <= MAX_MINUTES:
                out[r["id"]] = {"min": m, "km": round(rt["km"])}
            continue
        best = None
        for det in dict.fromkeys(d for c in closures if c["id"] in used for d in c["detours"]):
            stops = [src, detours[det], dst]
            alt = osrm.route(stops)
            if alt is None or alt["ferry"] or closures_on(alt["path"], stops, alt["km"], closures):
                continue
            m = minutes(alt["km"], alt["trains"])
            if best is None or m < best[0]:
                best = (m, alt, det)
        if best is None:
            log(f"{tag} over {used}, no open detour, dropped")
            continue
        m, alt, det = best
        if m <= MAX_MINUTES:
            log(f"{tag} over {used} {rt['km']:.0f} km -> via {det} {alt['km']:.0f} km"
                + (f" + {alt['trains']} car train" if alt["trains"] else ""))
            out[r["id"]] = {"min": m, "km": round(alt["km"]), "via": used}
    return out


def main(argv: list[str]) -> int:
    cities, resorts, closures, detours = load()
    osrm = Osrm()
    if argv:
        for c in [c for c in cities if c["id"] in argv]:
            rows = drive(osrm, c, resorts, closures, detours)
            for rid, v in sorted(rows.items(), key=lambda kv: kv[1]["min"]):
                print(f"{c['id']:14s} {rid:28s} {v['km']:5d} km {v['min'] / 60:5.1f} h  {' '.join(v.get('via', []))}")
        return 0
    table, via = {}, {}
    for i, c in enumerate(cities, 1):
        rows = drive(osrm, c, resorts, closures, detours)
        table[c["id"]] = {rid: v["min"] for rid, v in sorted(rows.items())}
        v = {rid: x["via"] for rid, x in sorted(rows.items()) if x.get("via")}
        if v:
            via[c["id"]] = v
        print(f"[{i}/{len(cities)}] {c['id']}: {len(rows)} resorts, {osrm.requests} requests so far", flush=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Road distance: OpenStreetMap via OSRM (router.project-osrm.org). "
                  f"Minutes = {BASE_MIN:.0f} + road km / {SPEED_KMH:.0f} km/h; no traffic, no weather.",
        "max_minutes": MAX_MINUTES,
        "closures": {c["id"]: c["name"] for c in closures},
        "targets": yaml.safe_load((ROOT / "data" / "drive_targets.yaml").read_text()) or {},
        "minutes": table,
        "via": via,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {sum(map(len, table.values()))} city-resort pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
