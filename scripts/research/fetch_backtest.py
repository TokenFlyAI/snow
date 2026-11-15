"""Download the phase-3 backtest set: SNOTEL daily observations and archived model forecasts.

    python scripts/research/fetch_backtest.py obs
    python scripts/research/fetch_backtest.py forecasts      # ~3,000 weighted Open-Meteo calls, resumable
    python scripts/research/fetch_backtest.py hires          # ~400 calls: ECMWF 9 km, winter 2025-26

Forecasts come from the Open-Meteo Previous Runs API: for every station and winter one request
with 5 models x (precipitation at leads 0,1,2,3,5,7 days + 2 m temperature and 10 m wind at lead 1).
Estimated weight per request = (40 variables / 10) x (181 days / 14) ~ 52.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "backtest"
UA = {"User-Agent": "snow-forecast-pipeline/0.1 (+https://github.com/TokenFlyAI/snow)"}

WINTERS = {"w2425": ("2024-11-01", "2025-04-30"), "w2526": ("2025-11-01", "2026-04-30")}
MODELS = ("ecmwf_ifs025", "gfs_global", "icon_global", "gem_global", "ncep_nbm_conus")
LEADS = (0, 1, 2, 3, 5, 7)
PAUSE_S = 9.0            # ~52 weighted calls per request -> under 400 per minute


def get(url: str, timeout: float = 180):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def hourly_vars() -> list[str]:
    v = ["precipitation"] + [f"precipitation_previous_day{n}" for n in LEADS if n]
    return v + ["temperature_2m_previous_day1", "wind_speed_10m_previous_day1"]


def fetch_obs(stations: list[dict]) -> None:
    out = RAW / "obs"
    out.mkdir(parents=True, exist_ok=True)
    for s in stations:
        f = out / (s["triplet"].replace(":", "_") + ".json")
        if f.exists():
            continue
        q = {"stationTriplets": s["triplet"], "elements": "WTEQ,SNWD,PREC,TOBS,TAVG,TMAX,TMIN", "duration": "DAILY",
             "beginDate": "2024-10-25", "endDate": "2026-05-05"}
        d = get("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?" + urllib.parse.urlencode(q))
        doc = {e["stationElement"]["elementCode"]: {"unit": e["stationElement"]["storedUnitCode"],
                                                    "values": {v["date"][:10]: v.get("value") for v in e["values"]}}
               for e in d[0]["data"]}
        f.write_text(json.dumps(doc, separators=(",", ":")))
        print(s["triplet"], s["name"], {k: len(v["values"]) for k, v in doc.items()})
        time.sleep(0.5)


def fetch_forecasts(stations: list[dict]) -> None:
    out = RAW / "fc"
    out.mkdir(parents=True, exist_ok=True)
    todo = [(s, w) for s in stations for w in WINTERS
            if not (out / f"{s['triplet'].replace(':', '_')}_{w}.json.gz").exists()]
    print(f"{len(todo)} requests to go", flush=True)
    for i, (s, w) in enumerate(todo):
        start, end = WINTERS[w]
        q = {"latitude": s["lat"], "longitude": s["lon"], "elevation": s["elevation_m"], "models": ",".join(MODELS),
             "hourly": ",".join(hourly_vars()), "start_date": start, "end_date": end, "timezone": "GMT",
             "wind_speed_unit": "kmh"}
        url = "https://previous-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)
        for attempt in range(5):
            try:
                d = get(url)
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:200]
                print(f"  HTTP {e.code} {body}", flush=True)
                if e.code != 429:
                    raise
                time.sleep(65 if "inutely" in body else 3700 if "ourly" in body else 65)
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"  {e}", flush=True)
                time.sleep(20)
        else:
            raise SystemExit("giving up")
        f = out / f"{s['triplet'].replace(':', '_')}_{w}.json.gz"
        with gzip.open(f, "wt") as fh:
            json.dump({"elevation": d.get("elevation"), "hourly": d["hourly"]}, fh, separators=(",", ":"))
        print(f"{i + 1}/{len(todo)} {s['triplet']} {w} {f.stat().st_size // 1024} KB", flush=True)
        time.sleep(PAUSE_S)


def fetch_hires(stations: list[dict]) -> None:
    """ECMWF IFS at its native 9 km grid (model id `ecmwf_ifs`): the archive has its leads from winter 2025-26 on."""
    out = RAW / "fc9"
    out.mkdir(parents=True, exist_ok=True)
    start, end = WINTERS["w2526"]
    for i, s in enumerate(stations):
        f = out / f"{s['triplet'].replace(':', '_')}_w2526.json.gz"
        if f.exists():
            continue
        q = {"latitude": s["lat"], "longitude": s["lon"], "elevation": s["elevation_m"], "models": "ecmwf_ifs",
             "hourly": ",".join(["precipitation"] + [f"precipitation_previous_day{n}" for n in LEADS if n]),
             "start_date": start, "end_date": end, "timezone": "GMT"}
        d = get("https://previous-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))
        with gzip.open(f, "wt") as fh:
            json.dump({"elevation": d.get("elevation"), "hourly": d["hourly"]}, fh, separators=(",", ":"))
        print(f"{i + 1}/{len(stations)} {s['triplet']} {f.stat().st_size // 1024} KB", flush=True)
        time.sleep(3.0)


if __name__ == "__main__":
    st = json.loads((RAW / "stations.json").read_text())
    {"obs": fetch_obs, "forecasts": fetch_forecasts, "hires": fetch_hires}[sys.argv[1]](st)
