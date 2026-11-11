"""Rebuild tests/fixtures/palisades_2024_03_blizzard.json.

Real case: the 28 Feb - 5 Mar 2024 Sierra Nevada blizzard at SNOTEL 784
(Palisades Tahoe, 2441 m). Archived model forecasts come from the Open-Meteo
Historical Forecast API, observations from the NRCS AWDB REST API.

    python scripts/make_backtest_fixture.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.ingest.open_meteo import hourly_vars  # noqa: E402

UA = {"User-Agent": "snow-forecast-pipeline/0.1 (+https://github.com/TokenFlyAI/snow)"}
STATION = "784:CA:SNTL"
START, END = "2024-02-28", "2024-03-05"
MODELS = ("gfs_global", "ecmwf_ifs025", "ncep_hrrr_conus")
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "palisades_2024_03_blizzard.json"


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.loads(r.read().decode())


def main() -> None:
    st = get(f"https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets={STATION}")[0]
    obs = get("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?"
              + urllib.parse.urlencode({"stationTriplets": STATION, "elements": "SNWD,WTEQ,PREC,TOBS",
                                        "duration": "DAILY", "beginDate": START, "endDate": "2024-03-06"}))
    observed = {e["stationElement"]["elementCode"]: {
        "unit": e["stationElement"]["storedUnitCode"],
        "values": {v["date"][:10]: v.get("value") for v in e["values"]}} for e in obs[0]["data"]}
    models = {}
    for m in MODELS:
        q = {"latitude": st["latitude"], "longitude": st["longitude"], "elevation": "nan", "models": m,
             "hourly": ",".join(hourly_vars()), "start_date": START, "end_date": END,
             "timezone": "GMT", "wind_speed_unit": "kmh"}
        d = get("https://historical-forecast-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))
        models[m] = {"elevation": d["elevation"], "hourly": d["hourly"]}
    doc = {
        "case": "Sierra Nevada blizzard, 28 Feb - 5 Mar 2024",
        "station": {"triplet": STATION, "name": st["name"], "lat": st["latitude"], "lon": st["longitude"],
                    "elevation_m": round(st["elevation"] * 0.3048)},
        "observed": observed,
        "models": models,
        "sources": ["Open-Meteo Historical Forecast API (CC BY 4.0)", "USDA NRCS AWDB / SNOTEL (public domain)"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
