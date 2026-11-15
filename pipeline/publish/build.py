"""Assemble the public JSON documents (canonical units: cm, mm, degC, m, km/h)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from ..config import (API_DAILY_LIMIT, API_DAILY_TARGET, DAILY_DAYS, ENSEMBLE_BY_ID, HOURLY_HORIZON_H, MODEL_BY_ID, NIGHT_START_H,
                      OUTLOOK_WEEKS, POINT_DAYS, SCHEMA_VERSION, SOURCES)
from ..process import aggregate
from ..process import ensemble as ens
from ..process.blend import (blend, daily_range, ensemble_agreement, ensemble_confidence, model_spread_confidence,
                             weights_for)
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


def resort_meta(resort: Resort, tier: str = "standard") -> dict:
    return {
        "tier": tier,
        "id": resort.id, "name": resort.name, "name_zh": resort.name_zh,
        "destination": resort.destination, "passes": dict(resort.passes),
        "country": resort.country, "state": resort.state, "region": resort.region,
        "lat": resort.lat, "lon": resort.lon,
        "elevation_m": resort.elevation_m.model_dump(), "timezone": resort.timezone,
        "snotel": resort.snotel, "needs_review": resort.needs_review,
    }


def _pct(x) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x), 2)


def _stats_by_level(values: np.ndarray, weights: np.ndarray, ratios: dict[str, float], thresholds) -> Optional[dict]:
    """Percentiles and probabilities of one day / window at the three elevations."""
    mid = ens.stats(values, weights, thresholds)
    if not mid.ok:
        return None
    by = {lv: ens.stats(values * ratios[lv], weights, thresholds) for lv in LEVELS}
    return {
        "p10": {lv: _r(by[lv].p10) for lv in LEVELS}, "p50": {lv: _r(by[lv].p50) for lv in LEVELS},
        "p90": {lv: _r(by[lv].p90) for lv in LEVELS}, "mean": {lv: _r(by[lv].mean) for lv in LEVELS},
        "prob": {f"{t:g}": {lv: _pct(by[lv].prob[t]) for lv in LEVELS} for t in thresholds},
        "n_members": mid.n_members,
    }


def build_resort(resort: Resort, derived: list[Derived], now: datetime,
                 missing_models: Optional[list[str]] = None, ens_raw: Optional[dict] = None,
                 tier: str = "standard") -> dict:
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

    # ---- daily block ------------------------------------------------------------
    # ski days D+0 .. D+9: point values from the blend, range + confidence from the ensembles
    # ski days D+10 .. D+15: ensemble probabilities only
    idx = aggregate.index_hours(ref, resort.timezone)
    today = now.astimezone(idx.local_start[0].tzinfo).date()
    dates = [today + timedelta(days=k) for k in range(max(DAILY_DAYS, 7 * max(OUTLOOK_WEEKS)))]
    point: list[dict] = []
    per_day_models: list[tuple[dict, np.ndarray]] = []       # ({level: per-model totals}, weights)
    by_model: dict[str, dict[str, list]] = {m: {lv: [] for lv in LEVELS} for m in ids}
    slr_by_day = np.full(len(dates), np.nan)
    for k in range(POINT_DAYS):
        d = dates[k]
        night, day, cal = aggregate.day_masks(idx, d)
        ski = night | day
        if not ski.any():
            break
        w_day = W[:, ski].mean(axis=1)
        entry: dict = {"date": d.isoformat(), "lead_days": k, "kind": "point"}
        snow_night, snow_day, total, per = {}, {}, {}, {}
        for lv in LEVELS:
            n_ = aggregate.window_sum(snow[lv], night)
            d_ = aggregate.window_sum(snow[lv], day)
            tot = n_ + d_ if np.isfinite(n_) and np.isfinite(d_) else float("nan")
            per[lv] = [aggregate.window_sum(snow_stack[lv][i], ski, min_coverage=0.9) for i in range(len(ids))]
            snow_night[lv], snow_day[lv], total[lv] = _r(n_), _r(d_), _r(tot)
        if total["mid"] is None:
            break  # beyond every model's horizon
        for lv in LEVELS:
            for m, v in zip(ids, per[lv]):
                by_model[m][lv].append(_r(v))
        per_day_models.append((per, w_day))
        entry["snow_night_cm"] = snow_night
        entry["snow_day_cm"] = snow_day
        entry["snow_cm"] = total
        entry["n_models"] = int(np.isfinite(per["mid"]).sum())
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
        slr_by_day[k] = aggregate.window_stat(slr_mid, ski, np.mean)
        s_mid = np.where(ski, np.nan_to_num(snow["mid"]), 0.0)
        if s_mid.sum() >= 0.5:
            slr_day = float(np.nansum(slr_mid * s_mid) / s_mid.sum())
            slr_by_day[k] = slr_day
            entry["slr"] = _r(slr_day)
            entry["quality"] = snow_quality(slr_day)
        else:
            entry["slr"] = None
            entry["quality"] = "none"
        point.append(entry)
    n_point = len(point)

    # ---- ensembles: calibrate against the blend, then percentiles / probabilities ----
    pool = ens.Pool.from_raw(ens_raw, dates)
    blend_mid = np.full(len(dates), np.nan)
    blend_mid[:n_point] = [e["snow_cm"]["mid"] for e in point]
    values, cal_info = ens.calibrate(pool, slr_by_day, blend_mid)
    weights = pool.weights

    def tot_lv(lv: str, days: range) -> float:
        return float(sum(point[k]["snow_cm"][lv] or 0.0 for k in days if k < n_point))

    # elevation ratio of the whole point period, used where a single day gives no information
    period_ratio = {lv: ens.level_ratio(tot_lv(lv, range(n_point)), tot_lv("mid", range(n_point))) for lv in LEVELS}
    if tot_lv("mid", range(n_point)) < 5.0:
        period_ratio = {lv: 1.0 for lv in LEVELS}

    def day_ratio(k: int) -> dict[str, float]:
        if k < n_point and (point[k]["snow_cm"]["mid"] or 0.0) >= 1.0:
            return {lv: ens.level_ratio(point[k]["snow_cm"][lv] or 0.0, point[k]["snow_cm"]["mid"]) for lv in LEVELS}
        return period_ratio

    daily: list[dict] = []
    for k in range(DAILY_DAYS):
        st = _stats_by_level(values[:, k], weights, day_ratio(k), ens.DAY_THRESHOLDS_CM) if pool.n_members else None
        if k < n_point:
            entry = point[k]
            per, w_day = per_day_models[k]
            low, high, source = {}, {}, "models"
            for lv in LEVELS:
                e_lo = st["p10"][lv] if st else None
                e_hi = st["p90"][lv] if st else None
                tot = entry["snow_cm"][lv]
                lo, hi, source = daily_range(tot if tot is not None else float("nan"),
                                             e_lo if e_lo is not None else float("nan"),
                                             e_hi if e_hi is not None else float("nan"), per[lv], w_day)
                low[lv], high[lv] = _r(lo), _r(hi)
            entry["snow_low_cm"], entry["snow_high_cm"], entry["range_source"] = low, high, source
            if st:
                agree = ensemble_agreement(entry["snow_cm"]["mid"], values[:, k], weights)
                st["agreement"] = _pct(agree)
                entry["confidence"] = ensemble_confidence(agree, k)
            else:
                entry["confidence"] = model_spread_confidence(per["mid"], w_day, k)
            entry["ens"] = st
            daily.append(entry)
        elif st:
            daily.append({"date": dates[k].isoformat(), "lead_days": k, "kind": "prob", "ens": st})
    for m in ids:
        for lv in LEVELS:
            by_model[m][lv] = by_model[m][lv][:n_point]

    # ---- weekly outlook (weeks 3-5), mid-mountain, probabilities only ----------------
    outlook = []
    for wk in OUTLOOK_WEEKS:
        days = range(7 * (wk - 1), 7 * wk)
        if not pool.n_members or days[-1] >= len(dates):
            continue
        tot = ens.window_totals(values, days)
        st = ens.stats(tot, weights, ens.WEEK_THRESHOLDS_CM)
        if not st.ok:
            continue
        used = np.isfinite(tot)
        outlook.append({
            "week": wk, "start": dates[days[0]].isoformat(), "end": dates[days[-1]].isoformat(),
            "p10_cm": _r(st.p10), "p50_cm": _r(st.p50), "p90_cm": _r(st.p90), "mean_cm": _r(st.mean),
            "prob": {f"{t:g}": _pct(st.prob[t]) for t in ens.WEEK_THRESHOLDS_CM},
            "n_members": st.n_members,
            "models": [m for m in pool.labels if any(u and x == m for u, x in zip(used, pool.model_of))],
        })

    # ---- summary ---------------------------------------------------------------
    summary: dict = {}
    for label, hours in (("24h", 24), ("72h", 72), ("7d", 168)):
        mask = (lead > 0) & (lead <= hours)
        summary[f"snow_{label}_cm"] = {lv: _r(float(np.nansum(snow[lv][mask]))) for lv in LEVELS}
    # ski-day totals (today's ski day started at 16:00 yesterday) with the ensemble range;
    # days without a point value contribute the ensemble mean
    fill = {0: blend_mid[0]} if n_point else None
    def window_cm(n_days: int) -> dict[str, float]:
        """Forecast total of the first n ski days: point values, then the ensemble mean."""
        cm = {}
        for lv in LEVELS:
            x = tot_lv(lv, range(n_days))
            for e in daily[n_point:n_days]:
                x += e["ens"]["mean"][lv] or 0.0
            cm[lv] = x
        return cm

    totals = {}
    for label, n_days in (("3d", 3), ("7d", 7), ("16d", DAILY_DAYS)):
        cm = window_cm(n_days)
        complete = len(daily) >= n_days
        ratios = {lv: ens.level_ratio(cm[lv], cm["mid"]) for lv in LEVELS}
        st = None
        if pool.n_members:
            st = _stats_by_level(ens.window_totals(values, range(n_days), fill=fill), weights, ratios, ())
        totals[label] = {
            "cm": {lv: _r(cm[lv]) for lv in LEVELS},
            "low_cm": {lv: _r(min(st["p10"][lv], cm[lv])) for lv in LEVELS} if st else None,
            "high_cm": {lv: _r(max(st["p90"][lv], cm[lv])) for lv in LEVELS} if st else None,
            "days": min(n_days, len(daily)), "complete": complete,
        }
    summary["totals"] = totals

    # ---- accumulation from today on: forecast line plus the spread of the members' own
    # accumulations (not a sum of daily percentiles), so the range widens with lead time
    cumulative: list[dict] = []
    if pool.n_members:
        keys = ("min", "p10", "p50", "p90", "max")
        prev = {key: {lv: 0.0 for lv in LEVELS} for key in keys}
        for k in range(len(daily)):
            tot = ens.window_totals(values, range(k + 1), fill=fill)
            fin = tot[np.isfinite(tot)]
            if fin.size < ens.MIN_MEMBERS:
                break
            cm = window_cm(k + 1)
            p10, p50, p90 = ens.weighted_quantiles(tot, weights, (0.1, 0.5, 0.9))
            mid = {"min": float(fin.min()), "p10": p10, "p50": p50, "p90": p90, "max": float(fin.max())}
            entry = {"date": dates[k].isoformat(), "lead_days": k, "n_members": int(fin.size),
                     "cm": {lv: _r(cm[lv]) for lv in LEVELS}}
            for key in keys:
                row = {}
                for lv in LEVELS:
                    x = mid[key] * ens.level_ratio(cm[lv], cm["mid"])
                    # the forecast line stays inside the fan; an accumulation never shrinks
                    x = min(x, cm[lv]) if key in ("min", "p10") else max(x, cm[lv]) if key in ("p90", "max") else x
                    row[lv] = prev[key][lv] = max(x, prev[key][lv])
                entry[key] = {lv: _r(row[lv]) for lv in LEVELS}
            cumulative.append(entry)
    summary["snow_16d_cm"] = totals["16d"]["cm"]
    # today's ski day ends at 16:00 local time: after that its snow is no longer "next"
    over = now.astimezone(idx.local_start[0].tzinfo).hour >= NIGHT_START_H
    nxt = next((e for e in point if (e["snow_cm"]["mid"] or 0) >= NEXT_SNOW_MIN_CM
                and not (over and e["lead_days"] == 0)), None)
    summary["next_snow"] = {"date": nxt["date"], "snow_cm": nxt["snow_cm"]} if nxt else None
    summary["daily_mid_cm"] = [e["snow_cm"]["mid"] for e in point]

    ensemble_info = None
    if pool.n_members:
        ensemble_info = {
            "generated_at": ens_raw.get("generated_at"),
            "level": "mid", "elevation_m": ens_raw.get("elevation_m"),
            "models": [{"id": mid, "label": pool.labels.get(mid, mid),
                        "members": sum(1 for x in pool.model_of if x == mid),
                        "horizon_days": int(np.flatnonzero(np.isfinite(values[[i for i, x in enumerate(pool.model_of) if x == mid]]).any(axis=0)).max()) + 1}
                       for mid in pool.models_on(range(len(dates)))],
            "calibration": {"factor": cal_info.factor, "slr_default": cal_info.slr_default, "days": cal_info.n_days,
                            "blend_cm": cal_info.blend_cm, "ensemble_cm": cal_info.ensemble_cm},
        }

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
        "resort": resort_meta(resort, tier),
        "units": {"snow": "cm", "precip": "mm", "temp": "C", "height": "m", "wind": "km/h"},
        "models": models,
        "ensemble": ensemble_info,
        "summary": summary,
        "hourly": hourly,
        # point days and probability-only days are kept apart, so a reader that only knows the
        # point-day fields (the phase-1 page shell) never meets an entry without them
        "daily": [e for e in daily if e["kind"] == "point"],
        "daily_prob": [e for e in daily if e["kind"] == "prob"],
        "outlook": outlook,
        "cumulative": cumulative,
        "by_model_daily_cm": by_model,
    }


def split_daily(doc: dict) -> dict:
    """Move probability-only days out of `daily` (documents published before `daily_prob` existed)."""
    if "daily_prob" not in doc:
        days = doc.get("daily", [])
        doc["daily"] = [e for e in days if e.get("kind", "point") == "point"]
        doc["daily_prob"] = [e for e in days if e.get("kind") == "prob"]
    return doc


def build_index(regions: list[Region], docs: list[dict], now: datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions": [r.model_dump() for r in regions],
        "resorts": [{**d["resort"], "generated_at": d["generated_at"],
                     "ensemble_at": (d.get("ensemble") or {}).get("generated_at"), "summary": d["summary"],
                     "dates": [e["date"] for e in d["daily"] if e.get("kind") == "point"],
                     "n_models": sum(1 for m in d["models"] if m["status"] == "ok"),
                     "n_members": sum(m["members"] for m in (d.get("ensemble") or {}).get("models", [])),
                     "outlook": [{"week": o["week"], "p50_cm": o["p50_cm"], "prob": o["prob"]} for o in d.get("outlook", [])]}
                    for d in docs],
    }


def build_manifest(now: datetime, model_status: dict[str, dict], n_resorts: int, usage: dict,
                   ensemble_status: Optional[dict[str, dict]] = None, run: Optional[dict] = None,
                   budget: Optional[dict] = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resort_count": n_resorts,
        "run": run or {},
        "models": [{"id": k, **v} for k, v in model_status.items()],
        "ensembles": [{"id": k, **v} for k, v in (ensemble_status or {}).items()],
        "api_usage": {"requests": usage.get("requests", 0),
                      "weighted_calls": round(usage.get("weighted_calls", 0.0), 1),
                      "by_kind": {k: round(v, 1) for k, v in usage.get("by_kind", {}).items()},
                      "daily_estimate": budget or {},
                      "daily_limit": API_DAILY_LIMIT, "daily_target": API_DAILY_TARGET},
        "sources": SOURCES,
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); model data from ECMWF, NOAA, DWD, ECCC, JMA, "
                       "Météo-France, MeteoSwiss, UK Met Office, CMA.",
    }
