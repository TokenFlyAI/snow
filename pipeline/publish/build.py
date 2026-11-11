"""Assemble the public JSON documents (canonical units: cm, mm, degC, m, km/h)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from ..config import FORECAST_DAYS, HOURLY_HORIZON_H, MODEL_BY_ID, SCHEMA_VERSION, SOURCES
from ..process import aggregate
from ..process.blend import blend, confidence, weighted_quantile, weights_for
from ..process.derive import Derived
from ..process.slr import snow_quality
from ..process.snowlevel import precip_type
from ..process.thermo import wind_chill
from ..resorts import LEVELS, Region, Resort

NEXT_SNOW_MIN_CM = 2.5  # one inch


def _r(x, nd: int = 1) -> Optional[float]:
    if x is None or not np.isfinite(x):
        return None
    v = round(float(x), nd)
    return int(v) if nd == 0 else v


def _list(a, nd: int = 1) -> list:
    return [_r(x, nd) for x in a]


def _iso(t64: np.datetime64) -> str:
    return str(t64.astype("datetime64[h]")) + ":00Z"


def _reindex(a: np.ndarray, src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    if src.shape == ref.shape and np.array_equal(src, ref):
        return a
    out = np.full(ref.shape, np.nan)
    pos = np.searchsorted(src, ref)
    ok = (pos < src.shape[0])
    ok[ok] &= src[pos[ok]] == ref[ok]
    out[ok] = a[pos[ok]]
    return out


def resort_meta(resort: Resort) -> dict:
    return {
        "id": resort.id, "name": resort.name, "name_zh": resort.name_zh,
        "destination": resort.destination, "passes": dict(resort.passes),
        "country": resort.country, "state": resort.state, "region": resort.region,
        "lat": resort.lat, "lon": resort.lon,
        "elevation_m": resort.elevation_m.model_dump(), "timezone": resort.timezone,
        "snotel": resort.snotel, "needs_review": resort.needs_review,
    }


def build_resort(resort: Resort, derived: list[Derived], now: datetime,
                 missing_models: Optional[list[str]] = None) -> dict:
    if not derived:
        raise ValueError(f"{resort.id}: no model data")
    ref = max((d.time for d in derived), key=lambda t: t.shape[0])
    ids = [d.model for d in derived]
    now64 = np.datetime64(now.astimezone(timezone.utc).replace(tzinfo=None), "h")
    lead = (ref - now64).astype("timedelta64[h]").astype(int)
    W = weights_for(ids, np.clip(lead, 0, None))

    def stack(get) -> np.ndarray:
        return np.stack([_reindex(get(d), d.time, ref) for d in derived])

    def B(get) -> np.ndarray:
        return blend(stack(get), W)

    temp = {lv: B(lambda d, lv=lv: d.temp[lv]) for lv in LEVELS}
    snow_stack = {lv: stack(lambda d, lv=lv: d.snow[lv]) for lv in LEVELS}
    snow = {lv: blend(snow_stack[lv], W) for lv in LEVELS}
    rain = {lv: B(lambda d, lv=lv: d.rain[lv]) for lv in LEVELS}
    frac = {lv: B(lambda d, lv=lv: d.frac_snow[lv]) for lv in LEVELS}
    slr_mid = B(lambda d: d.slr["mid"])
    precip = B(lambda d: d.precip)
    snow_level = B(lambda d: d.snow_level)
    fzl = B(lambda d: d.freezing_level)
    wind = B(lambda d: d.wind_summit)
    gust = B(lambda d: d.gust_summit)
    cloud = B(lambda d: d.cloud)
    vis = B(lambda d: d.visibility)
    feels = wind_chill(temp["summit"], wind)

    # ---- hourly block: next 168 h --------------------------------------------
    i0 = int(np.searchsorted(ref, now64, side="right"))
    sl_ = slice(i0, min(i0 + HOURLY_HORIZON_H, ref.shape[0]))
    hourly = {
        "time": [_iso(t) for t in ref[sl_]],
        "temp_c": {lv: _list(temp[lv][sl_]) for lv in LEVELS},
        "feels_summit_c": _list(feels[sl_]),
        "precip_mm": _list(precip[sl_], 2),
        "snow_cm": {lv: _list(snow[lv][sl_], 2) for lv in LEVELS},
        "ptype": {lv: [int(x) for x in precip_type(frac[lv][sl_])] for lv in LEVELS},
        "snow_level_m": _list(snow_level[sl_], 0),
        "freezing_level_m": _list(fzl[sl_], 0),
        "slr": _list(slr_mid[sl_]),
        "wind_summit_kmh": _list(wind[sl_], 0),
        "gust_summit_kmh": _list(gust[sl_], 0),
        "cloud_pct": _list(cloud[sl_], 0),
        "visibility_m": _list(vis[sl_], 0),
    }

    # ---- daily block: 16 ski days --------------------------------------------
    idx = aggregate.index_hours(ref, resort.timezone)
    today = now.astimezone(idx.local_start[0].tzinfo).date()
    daily = []
    by_model: dict[str, dict[str, list]] = {m: {lv: [] for lv in LEVELS} for m in ids}
    for k in range(FORECAST_DAYS):
        d = today + timedelta(days=k)
        night, day, cal = aggregate.day_masks(idx, d)
        ski = night | day
        if not ski.any():
            break
        w_day = W[:, ski].mean(axis=1) if ski.any() else np.ones(len(ids))
        entry: dict = {"date": d.isoformat(), "lead_days": k}
        snow_night, snow_day, total, low, high = {}, {}, {}, {}, {}
        model_totals_mid = []
        for lv in LEVELS:
            n_ = aggregate.window_sum(snow[lv], night)
            d_ = aggregate.window_sum(snow[lv], day)
            tot = n_ + d_ if np.isfinite(n_) and np.isfinite(d_) else float("nan")
            per_model = [aggregate.window_sum(snow_stack[lv][i], ski, min_coverage=0.9) for i in range(len(ids))]
            for m, v in zip(ids, per_model):
                by_model[m][lv].append(_r(v))
            lo = weighted_quantile(per_model, w_day, 0.1)
            hi = weighted_quantile(per_model, w_day, 0.9)
            if np.isfinite(tot):
                lo = min(lo, tot) if np.isfinite(lo) else tot
                hi = max(hi, tot) if np.isfinite(hi) else tot
            snow_night[lv], snow_day[lv], total[lv], low[lv], high[lv] = _r(n_), _r(d_), _r(tot), _r(lo), _r(hi)
            if lv == "mid":
                model_totals_mid = per_model
        if total["mid"] is None:
            break  # beyond every model's horizon
        entry["snow_night_cm"] = snow_night
        entry["snow_day_cm"] = snow_day
        entry["snow_cm"] = total
        entry["snow_low_cm"] = low
        entry["snow_high_cm"] = high
        entry["n_models"] = int(np.isfinite(model_totals_mid).sum())
        entry["confidence"] = confidence(model_totals_mid, w_day, k)
        entry["precip_mm"] = _r(aggregate.window_sum(precip, ski))
        entry["rain_base_mm"] = _r(aggregate.window_sum(rain["base"], ski))
        entry["temp_max_c"] = {lv: _r(aggregate.window_stat(temp[lv], cal, np.max)) for lv in ("base", "summit")}
        entry["temp_min_c"] = {lv: _r(aggregate.window_stat(temp[lv], cal, np.min)) for lv in ("base", "summit")}
        wet = ski & (np.nan_to_num(precip) >= 0.1)
        sl_mask = wet if wet.sum() >= 2 else ski
        entry["snow_level_m"] = {
            "min": _r(aggregate.window_stat(snow_level, sl_mask, np.min), 0),
            "max": _r(aggregate.window_stat(snow_level, sl_mask, np.max), 0),
            "during_precip": bool(wet.sum() >= 2),
        }
        entry["freezing_level_m"] = _r(aggregate.window_stat(fzl, ski, np.mean), 0)
        entry["gust_max_kmh"] = _r(aggregate.window_stat(gust, day if day.any() else cal, np.max), 0)
        entry["wind_avg_kmh"] = _r(aggregate.window_stat(wind, day if day.any() else cal, np.mean), 0)
        entry["cloud_pct"] = _r(aggregate.window_stat(cloud, day if day.any() else cal, np.mean), 0)
        s_mid = np.where(ski, np.nan_to_num(snow["mid"]), 0.0)
        if s_mid.sum() >= 0.5:
            slr_day = float(np.nansum(slr_mid * s_mid) / s_mid.sum())
            entry["slr"] = _r(slr_day)
            entry["quality"] = snow_quality(slr_day)
        else:
            entry["slr"] = None
            entry["quality"] = "none"
        daily.append(entry)
    n_days = len(daily)
    for m in ids:
        for lv in LEVELS:
            by_model[m][lv] = by_model[m][lv][:n_days]

    # ---- summary ---------------------------------------------------------------
    summary: dict = {}
    for label, hours in (("24h", 24), ("72h", 72), ("7d", 168), ("16d", 10 ** 6)):
        mask = (lead > 0) & (lead <= hours)
        summary[f"snow_{label}_cm"] = {lv: _r(float(np.nansum(snow[lv][mask]))) for lv in LEVELS}
    nxt = next((e for e in daily if (e["snow_cm"]["mid"] or 0) >= NEXT_SNOW_MIN_CM), None)
    summary["next_snow"] = {"date": nxt["date"], "snow_cm": nxt["snow_cm"]} if nxt else None
    summary["daily_mid_cm"] = [e["snow_cm"]["mid"] for e in daily]

    models = []
    for d in derived:
        p = _reindex(d.precip, d.time, ref)
        fin = np.flatnonzero(np.isfinite(p))
        spec = MODEL_BY_ID.get(d.model)
        models.append({
            "id": d.model, "label": spec.label if spec else d.model, "kind": spec.kind if spec else "",
            "status": "ok", "grid_elevation_m": _r(d.grid_elevation, 0),
            "horizon_h": int(max(lead[fin[-1]], 0)) if fin.size else 0,
            "has_profile": d.has_profile,
        })
    for m in missing_models or []:
        spec = MODEL_BY_ID.get(m)
        models.append({"id": m, "label": spec.label if spec else m, "kind": spec.kind if spec else "",
                       "status": "missing"})

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resort": resort_meta(resort),
        "units": {"snow": "cm", "precip": "mm", "temp": "C", "height": "m", "wind": "km/h"},
        "models": models,
        "summary": summary,
        "hourly": hourly,
        "daily": daily,
        "by_model_daily_cm": by_model,
    }


def build_index(regions: list[Region], docs: list[dict], now: datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions": [r.model_dump() for r in regions],
        "resorts": [{**d["resort"], "summary": d["summary"],
                     "dates": [e["date"] for e in d["daily"]],
                     "n_models": sum(1 for m in d["models"] if m["status"] == "ok")} for d in docs],
    }


def build_manifest(now: datetime, model_status: dict[str, dict], n_resorts: int, usage: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resort_count": n_resorts,
        "models": [{"id": k, **v} for k, v in model_status.items()],
        "api_usage": {"requests": usage.get("requests", 0),
                      "weighted_calls": round(usage.get("weighted_calls", 0.0), 1)},
        "sources": SOURCES,
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); model data from ECMWF, NOAA, DWD, ECCC, JMA.",
    }
