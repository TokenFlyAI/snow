"""planner.json: the compact decision data behind the Powder Planner page (design doc B1).

One file instead of 229 resort documents (~8 MB): per resort, each ski day's numbers the planner
ranks and shows, plus the powder score. Everything else (filters, ranking, the go / wait hint) is
done in the browser.

The powder score follows docs/phase3-accuracy-and-planner.md section 4.4 as revised by the planner
backtest (docs/phase3-planner-validation.md): it ranks by snowfall (rain and wind already priced in),
is not capped, and is an expectation over the ensemble spread. Every constant is a starting value
to be tuned once observations are archived (A1-A3).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..config import SCHEMA_VERSION

PLANNER_VERSION = 1

# ---- powder score (empirical starting values) -------------------------------------------------
SCORE_PER_CM = 4.0            # 25 cm of fresh snow at opening scores 100; not capped
CARRY_DAYTIME = 0.5           # snow that fell during yesterday's lift hours counts half (part is tracked out)
QUALITY_FACTOR = {"powder": 1.1, "packed": 1.0, "heavy": 0.8, "none": 1.0}
RAIN_BASE_MM = 2.0            # rain at the base on the day ...
RAIN_BASE_FACTOR = 0.8
RAIN_MID_FACTOR = 0.5         # ... or the snow level above mid-mountain while it precipitates
RAIN_MID_MIN_PRECIP_MM = 2.0
GUST_FACTORS = ((100.0, 0.5), (70.0, 0.8))   # summit gust km/h above which lifts may close
ENSEMBLE_WEIGHTS = (0.3, 0.4, 0.3)           # p10 / p50 / p90
# The blend is the better point forecast (backtest: 4-16 % lower error than NBM), so a wide ensemble
# mostly discounts a day; its upside lifts the score by at most 10 %.
ENSEMBLE_RATIO_BOUNDS = (0.25, 1.1)

POINT_FIELDS = ("date", "lead", "score", "fresh", "night", "cm", "low", "high", "p2_5", "p15",
                "quality", "gust", "rain", "rain_mid", "conf")
PROB_FIELDS = ("date", "lead", "p2_5", "p15", "p50")
META_FIELDS = ("name", "name_zh", "destination", "region", "country", "state", "lat", "lon", "timezone",
               "tier", "passes", "mid_m")


def _num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) else None


def raw_score(fresh_cm: float, quality: Optional[str], rain_base_mm: Optional[float], rain_mid: bool,
              gust_kmh: Optional[float]) -> float:
    """Powder score of one morning from its point forecast."""
    s = SCORE_PER_CM * max(0.0, fresh_cm)
    s *= QUALITY_FACTOR.get(quality or "none", 1.0)
    if rain_mid:
        s *= RAIN_MID_FACTOR
    elif (rain_base_mm or 0.0) >= RAIN_BASE_MM:
        s *= RAIN_BASE_FACTOR
    for limit, f in GUST_FACTORS:
        if (gust_kmh or 0.0) > limit:
            s *= f
            break
    return s


def ensemble_ratio(total_cm: Optional[float], p10: Optional[float], p50: Optional[float],
                   p90: Optional[float]) -> float:
    """Ensemble-weighted amount relative to the point value: below 1 when the members mostly see less."""
    if total_cm is None or total_cm < 1.0 or None in (p10, p50, p90):
        return 1.0
    a, b, c = ENSEMBLE_WEIGHTS
    lo, hi = ENSEMBLE_RATIO_BOUNDS
    return min(hi, max(lo, (a * p10 + b * p50 + c * p90) / total_cm))


def rain_at_mid(day: dict, mid_m: Optional[float]) -> bool:
    sl = day.get("snow_level_m") or {}
    top = _num(sl.get("max"))
    return bool(mid_m is not None and top is not None and sl.get("during_precip")
                and (day.get("precip_mm") or 0.0) >= RAIN_MID_MIN_PRECIP_MM and top > mid_m)


def planner_days(doc: dict) -> tuple[list[list], list[list]]:
    """(point rows, probability-only rows) of one resort document, columns as in POINT_FIELDS / PROB_FIELDS."""
    mid_m = _num(((doc.get("resort") or {}).get("elevation_m") or {}).get("mid"))
    points, prev_day = [], 0.0
    for e in doc.get("daily", []):
        g = lambda key: ((e.get(key) or {}).get("mid"))  # noqa: E731
        night, day, cm = g("snow_night_cm") or 0.0, g("snow_day_cm") or 0.0, g("snow_cm")
        ens = e.get("ens") or {}
        q = lambda key: ((ens.get(key) or {}).get("mid"))  # noqa: E731
        prob = ens.get("prob") or {}
        fresh = night + CARRY_DAYTIME * prev_day
        rmid = rain_at_mid(e, mid_m)
        score = raw_score(fresh, e.get("quality"), e.get("rain_base_mm"), rmid, e.get("gust_max_kmh"))
        score *= ensemble_ratio(cm, q("p10"), q("p50"), q("p90"))
        points.append([e["date"], e["lead_days"], round(score), round(fresh, 1), round(night, 1), cm,
                       g("snow_low_cm"), g("snow_high_cm"), (prob.get("2.5") or {}).get("mid"),
                       (prob.get("15") or {}).get("mid"), e.get("quality"), e.get("gust_max_kmh"),
                       e.get("rain_base_mm"), int(rmid), e.get("confidence")])
        prev_day = day
    probs = []
    for e in doc.get("daily_prob", []):
        ens = e.get("ens") or {}
        prob = ens.get("prob") or {}
        probs.append([e["date"], e["lead_days"], (prob.get("2.5") or {}).get("mid"),
                      (prob.get("15") or {}).get("mid"), (ens.get("p50") or {}).get("mid")])
    return points, probs


def build_planner(regions: list, docs: list[dict], now: datetime) -> dict:
    resorts = {}
    for d in docs:
        m = d["resort"]
        points, probs = planner_days(d)
        meta = {k: m.get(k) for k in META_FIELDS if k != "mid_m"}
        meta["mid_m"] = (m.get("elevation_m") or {}).get("mid")
        resorts[m["id"]] = {**meta, "generated_at": d.get("generated_at"), "days": points, "prob_days": probs}
    return {
        "schema_version": SCHEMA_VERSION,
        "planner_version": PLANNER_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": {"snow": "cm", "precip": "mm", "wind": "km/h", "height": "m"},
        "fields": list(POINT_FIELDS),
        "prob_fields": list(PROB_FIELDS),
        "regions": [r if isinstance(r, dict) else r.model_dump() for r in regions],
        "resorts": resorts,
    }
