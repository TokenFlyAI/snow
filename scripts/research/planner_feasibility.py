"""Feasibility checks for the Powder Planner, on real data.

    python scripts/research/planner_feasibility.py prototype   # live ranking + size of a compact planner.json
    python scripts/research/planner_feasibility.py drive       # straight-line estimate against OSRM road times
    python scripts/research/planner_feasibility.py history     # powder days per pass and region, 10 winters of SNOTEL

Nothing here calls Open-Meteo: live forecasts come from the published GitHub Pages data,
road times from the public OSRM demo server, history from the NRCS AWDB API.
"""
from __future__ import annotations

import concurrent.futures as cf
import gzip
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "backtest"
BASE = "https://tokenflyai.github.io/snow/data/v1/"
UA = {"User-Agent": "snow-forecast-pipeline/0.1 (+https://github.com/TokenFlyAI/snow)"}
CITIES = {"San Francisco": (37.77, -122.42), "Salt Lake City": (40.76, -111.89), "Denver": (39.74, -104.99),
          "Seattle": (47.61, -122.33)}


def get(url: str, timeout: float = 60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def drive_h(lat1, lon1, lat2, lon2) -> float:
    """First-cut drive time: straight line x 1.3 at 90 km/h."""
    return km(lat1, lon1, lat2, lon2) * 1.3 / 90.0


# --------------------------------------------------------------------------- powder score (design doc, section 4.4)
def powder_score(night_cm, prev_day_cm, slr, rain_base_mm, gust_kmh) -> float:
    fresh = (night_cm or 0.0) + 0.5 * (prev_day_cm or 0.0)
    score = min(100.0, fresh * 4.0)
    score *= 1.1 if (slr or 0) >= 14 else 0.8 if (slr or 99) < 9 else 1.0
    if (rain_base_mm or 0.0) >= 2.0:
        score *= 0.8
    if (gust_kmh or 0.0) > 100:
        score *= 0.5
    elif (gust_kmh or 0.0) > 70:
        score *= 0.8
    return score


def prototype() -> None:
    idx = get(BASE + "resorts.json")
    with cf.ThreadPoolExecutor(12) as ex:
        docs = [d for d in ex.map(lambda r: _try(BASE + f"resort/{r['id']}.json"), idx["resorts"]) if d]
    rows, compact = [], {}
    for d in docs:
        m = d["resort"]
        days = d["daily"]
        entry = []
        for k, e in enumerate(days):
            prev = days[k - 1]["snow_day_cm"]["mid"] if k else 0.0
            sc = powder_score(e["snow_night_cm"]["mid"], prev, e.get("slr"), e.get("rain_base_mm"), e.get("gust_max_kmh"))
            p15 = ((e.get("ens") or {}).get("prob") or {}).get("15", {}).get("mid")
            entry.append([e["date"], round(sc), e["snow_cm"]["mid"], e["snow_low_cm"]["mid"], e["snow_high_cm"]["mid"],
                          e["snow_night_cm"]["mid"], p15, e.get("quality"), e.get("gust_max_kmh"), e.get("rain_base_mm"),
                          e.get("confidence")])
            rows.append({"id": m["id"], "name": m["name"], "passes": m.get("passes", {}), "lat": m["lat"], "lon": m["lon"],
                         "date": e["date"], "lead": e["lead_days"], "score": sc, "snow_cm": e["snow_cm"]["mid"],
                         "low": e["snow_low_cm"]["mid"], "high": e["snow_high_cm"]["mid"], "night_cm": e["snow_night_cm"]["mid"],
                         "p15": p15, "quality": e.get("quality"), "gust": e.get("gust_max_kmh"), "conf": e.get("confidence")})
        compact[m["id"]] = entry
    blob = json.dumps({"generated_at": idx["generated_at"], "fields": ["date", "score", "cm", "low", "high", "night", "p15", "quality", "gust", "rain", "conf"],
                       "resorts": compact}, separators=(",", ":")).encode()
    print(f"{len(docs)} resorts; compact planner.json: {len(blob) / 1024:.0f} KB raw, {len(gzip.compress(blob)) / 1024:.0f} KB gzip "
          f"(the {len(docs)} resort documents it replaces: {sum(len(json.dumps(d)) for d in docs) / 1e6:.1f} MB)")
    for who, city, pass_, max_h in (("Ikon, San Francisco, 4.5 h", "San Francisco", "ikon", 4.5), ("Epic, Denver, 3 h", "Denver", "epic", 3.0),
                                    ("Ikon, Seattle, 3 h", "Seattle", "ikon", 3.0)):
        la, lo = CITIES[city]
        pick = [r for r in rows if pass_ in r["passes"] and 1 <= r["lead"] <= 7 and drive_h(la, lo, r["lat"], r["lon"]) <= max_h]
        pick.sort(key=lambda r: -r["score"])
        print(f"\n{who}: {len({r['id'] for r in pick})} resorts in range, top rows of the next 7 days")
        print("  %-22s %-10s %5s %7s %11s %5s %8s %6s %6s  %s" % ("resort", "date", "score", "snow", "range", "P>=6in", "quality", "gust", "drive", "confidence"))
        for r in pick[:8]:
            print("  %-22s %-10s %5.0f %6.0f\" %4.0f-%-4.0f\" %5s %8s %5.0f %5.1fh  %s" % (
                r["name"][:22], r["date"], r["score"], r["snow_cm"] / 2.54, (r["low"] or 0) / 2.54, (r["high"] or 0) / 2.54,
                "-" if r["p15"] is None else f"{100 * r['p15']:.0f}%", r["quality"], r["gust"] or 0,
                drive_h(la, lo, r["lat"], r["lon"]), r["conf"]))


def _try(url):
    try:
        return get(url)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- drive time
def drive() -> None:
    resorts = yaml.safe_load((ROOT / "data" / "resorts.yaml").read_text())["resorts"]
    err = []
    for city, (la, lo) in CITIES.items():
        near = [r for r in resorts if 60 < km(la, lo, r["lat"], r["lon"]) < 450][:25]
        coords = ";".join([f"{lo},{la}"] + [f"{r['lon']},{r['lat']}" for r in near])
        d = get(f"https://router.project-osrm.org/table/v1/driving/{coords}?sources=0&annotations=duration,distance")
        print(f"\n{city}: {len(near)} resorts")
        for r, sec, m in zip(near, d["durations"][0][1:], d["distances"][0][1:]):
            if sec is None:
                continue
            est, osrm = drive_h(la, lo, r["lat"], r["lon"]), sec / 3600.0
            err.append((est - osrm, est / osrm))
            print("  %-26s straight line %4.0f km, road %4.0f km; estimate %4.1f h, OSRM %4.1f h (%+.0f%%)" % (
                r["name"][:26], km(la, lo, r["lat"], r["lon"]), m / 1000.0, est, osrm, 100 * (est / osrm - 1)))
    e = sorted(abs(a) for a, _ in err)
    ratio = sorted(b for _, b in err)
    print(f"\n{len(err)} pairs: median |error| {e[len(e) // 2] * 60:.0f} min, 90th percentile {e[int(len(e) * 0.9)] * 60:.0f} min; "
          f"estimate / OSRM median {ratio[len(ratio) // 2]:.2f}, range {ratio[0]:.2f}-{ratio[-1]:.2f}")


# --------------------------------------------------------------------------- 10 winters of powder days per pass
def history() -> None:
    stations = json.loads((RAW / "stations.json").read_text())
    passes = {r["id"]: r.get("passes", {}) for r in yaml.safe_load((ROOT / "data" / "resorts.yaml").read_text())["resorts"]}
    out = RAW / "obs10"
    out.mkdir(exist_ok=True)
    powder: dict[str, dict[str, set]] = {}                 # station -> winter -> set of powder dates
    for s in stations:
        f = out / (s["triplet"].replace(":", "_") + ".json")
        if not f.exists():
            q = {"stationTriplets": s["triplet"], "elements": "PREC,TAVG", "duration": "DAILY",
                 "beginDate": "2016-10-25", "endDate": "2026-05-05"}
            d = get("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?" + urllib.parse.urlencode(q), 180)
            f.write_text(json.dumps({e["stationElement"]["elementCode"]: {v["date"][:10]: v.get("value") for v in e["values"]}
                                     for e in d[0]["data"]}, separators=(",", ":")))
        o = json.loads(f.read_text())
        prec, tavg = o.get("PREC", {}), o.get("TAVG", {})
        days = sorted(prec)
        by = defaultdict(set)
        for a, b in zip(days, days[1:]):
            d = date.fromisoformat(b)
            if d.month not in (11, 12, 1, 2, 3, 4) or prec[a] is None or prec[b] is None:
                continue
            t = tavg.get(b)
            if (prec[b] - prec[a]) * 25.4 >= 12.7 and (t is None or (t - 32) / 1.8 <= 0.5):
                by[f"{d.year - 1 if d.month < 6 else d.year}-{str(d.year if d.month < 6 else d.year + 1)[2:]}"].add(b)
        powder[s["triplet"]] = by
    winters = sorted({w for by in powder.values() for w in by})
    print("Powder days (>= 12.7 mm of water, mean temperature <= 0.5 C) on at least one mountain of the pass, per winter")
    print("%-18s %-5s %-3s " % ("region", "pass", "n") + " ".join(w[2:] for w in winters) + "   mean")
    for reg in ("tahoe", "utah", "colorado", "pnw", "northern-rockies"):
        for p in ("ikon", "epic"):
            st = [s["triplet"] for s in stations if s["region"] == reg and any(p in passes.get(r["id"], {}) for r in s["resorts"])]
            if not st:
                continue
            counts = [len(set().union(*(powder[t].get(w, set()) for t in st))) for w in winters]
            print("%-18s %-5s %-3d " % (reg, p, len(st)) + " ".join("%5d" % c for c in counts) + "   %.1f" % (sum(counts) / len(counts)))


if __name__ == "__main__":
    {"prototype": prototype, "drive": drive, "history": history}[sys.argv[1]]()
