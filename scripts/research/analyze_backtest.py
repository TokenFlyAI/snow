"""Phase-3 backtest: do the proposed corrections actually help?

    python scripts/research/analyze_backtest.py            # prints tables, writes raw/backtest/results.json + PNGs

Data: 29 SNOTEL stations next to US-West resorts, winters 2024-25 and 2025-26 (Nov-Apr),
archived forecasts of 5 models at leads 0,1,2,3,5,7 days (Open-Meteo Previous Runs API).
Everything is evaluated out of sample: train on one winter, test on the other, both ways.

Truth for liquid precipitation on day D (midnight to midnight, station time): the increase of
the accumulated-precipitation gauge (PREC). It is quality controlled and monotone; the snow pillow
(WTEQ) flutters by one 0.1 in tick, so "max(gauge, pillow)" would inflate the totals. Gauges miss
some snow in wind, so every bias number here is relative to the gauge. `--truth max` shows the
sensitivity to that choice.
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.config import BLEND_WEIGHTS  # noqa: E402
from pipeline.process.slr import kuchera_slr, wind_factor  # noqa: E402

RAW = ROOT / "raw" / "backtest"
WINTERS = {"w2425": ("2024-11-01", "2025-04-30"), "w2526": ("2025-11-01", "2026-04-30")}
MODELS = ("ecmwf_ifs025", "gfs_global", "icon_global", "gem_global", "ncep_nbm_conus")
LABEL = {"ecmwf_ifs025": "ECMWF", "gfs_global": "GFS", "icon_global": "ICON", "gem_global": "GEM", "ncep_nbm_conus": "NBM"}
HAND_ID = {"icon_global": "icon_seamless"}          # name used in config.BLEND_WEIGHTS
LEADS = (0, 1, 2, 3, 5, 7)
# The archive's GFS precipitation at leads of 5 and 7 days sums to 0.44 and 0.31 of the observed total
# while leads 0-3 sum to 1.0: an artefact of how the 3-hourly part of the run is stored, not GFS skill.
BROKEN = {("gfs_global", 5), ("gfs_global", 7)}
IN = 25.4
WET_MM = 2.5
RNG = np.random.default_rng(7)
TRUTH = "max" if "--truth" in sys.argv and sys.argv[sys.argv.index("--truth") + 1] == "max" else "gauge"


# --------------------------------------------------------------------------- load
def load() -> dict:
    stations = json.loads((RAW / "stations.json").read_text())
    tz = {s["stationTriplet"]: s.get("dataTimeZone", -8.0) for s in json.loads((RAW / "snotel_stations.json").read_text())}
    rows = []
    for si, s in enumerate(stations):
        key = s["triplet"].replace(":", "_")
        obs = json.loads((RAW / "obs" / f"{key}.json").read_text())
        val = lambda el, d: obs.get(el, {}).get("values", {}).get(d.isoformat())  # noqa: E731
        off = timedelta(hours=-tz.get(s["triplet"], -8.0))          # local midnight in UTC
        for wi, w in enumerate(WINTERS):
            f = RAW / "fc" / f"{key}_{w}.json.gz"
            if not f.exists():
                continue
            h = json.load(gzip.open(f))["hourly"]
            f9 = RAW / "fc9" / f"{key}_{w}.json.gz"          # ECMWF at 9 km, only winter 2025-26
            h9 = json.load(gzip.open(f9))["hourly"] if f9.exists() else None
            a9 = lambda name: np.array([np.nan if x is None else x for x in (h9 or {}).get(name, [])], dtype=float)  # noqa: E731
            t = np.array(h["time"], dtype="datetime64[h]")
            arr = lambda name: np.array([np.nan if x is None else x for x in h.get(name, [])], dtype=float)  # noqa: E731
            d0, d1 = (date.fromisoformat(x) for x in WINTERS[w])
            d = d0 + timedelta(days=1)
            while d < d1:
                nxt = d + timedelta(days=1)
                a = np.datetime64(datetime(d.year, d.month, d.day) + off, "h")
                mask = (t > a) & (t <= a + np.timedelta64(24, "h"))
                # AWDB daily values carry the reading at the END of the labelled day (checked: the lagged
                # correlation with the forecasts peaks at 0.9 for this window and is 0.45 one day off)
                prv = d - timedelta(days=1)
                d_prec = _inc(val("PREC", prv), val("PREC", d))
                d_swe = _inc(val("WTEQ", prv), val("WTEQ", d))
                d_dep = _inc(val("SNWD", prv), val("SNWD", d), allow_neg=True)
                if mask.sum() == 24 and d_prec is not None:
                    row = {"s": si, "w": wi, "date": d.isoformat(), "region": s["region"], "elev": s["elevation_m"],
                           "obs": (max(d_prec, d_swe or 0.0) if TRUTH == "max" else d_prec) * IN,
                           "swe": np.nan if d_swe is None else d_swe * IN, "prec": np.nan if d_prec is None else d_prec * IN,
                           "depth": np.nan if d_dep is None else d_dep * 2.54, "tavg": _f2c(val("TAVG", d)),
                           "month": d.month}
                    for m in MODELS:
                        for L in LEADS:
                            name = f"precipitation_{m}" if L == 0 else f"precipitation_previous_day{L}_{m}"
                            x = arr(name)
                            v = x[mask] if x.size else np.array([np.nan])
                            row[f"{m}|{L}"] = float(v.sum()) if np.isfinite(v).all() and (m, L) not in BROKEN else np.nan
                            if (m, L) in BROKEN:
                                row[f"raw|{m}|{L}"] = float(v.sum()) if np.isfinite(v).all() else np.nan
                    for L in LEADS:
                        x = a9("precipitation" if L == 0 else f"precipitation_previous_day{L}")
                        v = x[mask] if x.size else np.array([np.nan])
                        row[f"ecmwf_ifs|{L}"] = float(v.sum()) if np.isfinite(v).all() else np.nan
                    for m in MODELS:
                        for var, k in (("temperature_2m", "t"), ("wind_speed_10m", "wind")):
                            x = arr(f"{var}_previous_day1_{m}")
                            v = x[mask] if x.size else np.array([np.nan])
                            row[f"{m}|{k}"] = float(np.nanmean(v)) if np.isfinite(v).sum() >= 18 else np.nan
                    rows.append(row)
                d = nxt
    keys = set().union(*(r.keys() for r in rows[:50]))
    cols = {k: np.array([r.get(k, np.nan) for r in rows]) for k in keys}
    cols["_stations"] = stations
    return cols


def _inc(a, b, allow_neg=False):
    if a is None or b is None:
        return None
    return (b - a) if allow_neg else max(b - a, 0.0)


def _f2c(x):
    return np.nan if x is None else (x - 32.0) / 1.8


# --------------------------------------------------------------------------- scores
def mae(f, o, m=None):
    ok = np.isfinite(f) & np.isfinite(o) if m is None else np.isfinite(f) & np.isfinite(o) & m
    return float(np.abs(f[ok] - o[ok]).mean()) if ok.any() else float("nan")


def boot_diff(f_new, f_old, o, stations, m, n=1000):
    """Station-block bootstrap of the relative MAE change of f_new against f_old (negative = better)."""
    ok = np.isfinite(f_new) & np.isfinite(f_old) & np.isfinite(o) & m
    ids = np.unique(stations[ok])
    e_new, e_old = np.abs(f_new - o), np.abs(f_old - o)
    per = {i: (e_new[ok & (stations == i)].sum(), e_old[ok & (stations == i)].sum()) for i in ids}
    out = []
    for _ in range(n):
        pick = RNG.choice(ids, ids.size)
        a = sum(per[i][0] for i in pick)
        b = sum(per[i][1] for i in pick)
        out.append(a / b - 1.0)
    return float(np.percentile(out, 5)), float(np.percentile(out, 95))


# --------------------------------------------------------------------------- methods
def hand_weights(L: int) -> dict[str, float]:
    hours = L * 24 + 12
    row = next(w for bound, w in BLEND_WEIGHTS if hours < bound)
    return {m: row.get(HAND_ID.get(m, m), 0.0) for m in MODELS}


def blend(c, L, weights: dict[str, float], factor=None):
    """Weighted mean over the models that have a value; `factor[m]` is a per-row multiplier."""
    num = np.zeros(c["obs"].size)
    den = np.zeros(c["obs"].size)
    for m in MODELS:
        x = c[f"{m}|{L}"] * (factor[m] if factor else 1.0)
        ok = np.isfinite(x) & (weights[m] > 0)
        num[ok] += weights[m] * x[ok]
        den[ok] += weights[m]
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)


def fit_bias(c, L, train, k_mm=150.0):
    """Multiplicative bias per model: station factor shrunk to the region factor, region to the global one."""
    out = {}
    for m in MODELS:
        f, o = c[f"{m}|{L}"], c["obs"]
        ok = train & np.isfinite(f) & np.isfinite(o)
        g = o[ok].sum() / max(f[ok].sum(), 1e-6) if ok.any() else 1.0
        fac = np.full(o.size, g)
        for reg in np.unique(c["region"]):
            r = ok & (c["region"] == reg)
            fr = (o[r].sum() + 3 * k_mm * g) / (f[r].sum() + 3 * k_mm)
            for s in np.unique(c["s"][c["region"] == reg]):
                x = r & (c["s"] == s)
                fs = (o[x].sum() + k_mm * fr) / (f[x].sum() + k_mm)
                fac[c["s"] == s] = fs
        out[m] = np.clip(fac, 0.5, 2.0)
    return out


def fit_weights(c, L, train, factor, floor=0.03):
    """Non-negative least squares on the bias-corrected models (rows where all models exist)."""
    have = [m for m in MODELS if np.isfinite(c[f"{m}|{L}"][train]).mean() > 0.5]      # ICON stops before day 7
    X = np.stack([c[f"{m}|{L}"] * factor[m] for m in have], axis=1)
    ok = train & np.isfinite(X).all(axis=1) & np.isfinite(c["obs"])
    w, _ = nnls(X[ok], c["obs"][ok], maxiter=2000)
    w = np.maximum(w, floor * w.sum()) if w.sum() > 0 else np.ones(len(have))
    out = {m: 0.0 for m in MODELS}
    out.update(dict(zip(have, w / w.sum())))
    return out, float(w.sum())


def oos(c, fn):
    """Train on one winter, predict the other, both ways; returns one out-of-sample array."""
    out = np.full(c["obs"].size, np.nan)
    for test_w in (0, 1):
        train, test = c["w"] != test_w, c["w"] == test_w
        out[test] = fn(train)[test]
    return out


# --------------------------------------------------------------------------- experiments
def exp_precip(c) -> dict:
    o, wet = c["obs"], c["obs"] >= WET_MM
    res = {"leads": list(LEADS), "mae_wet": {}, "mae_all": {}, "bias": {}, "weights": {}, "ci": {}}
    preds = {}
    for L in LEADS:
        p = {LABEL[m]: c[f"{m}|{L}"] for m in MODELS}
        p["equal"] = blend(c, L, {m: 1.0 for m in MODELS})
        p["hand (v2)"] = blend(c, L, hand_weights(L))
        p["bias-corrected"] = oos(c, lambda tr, L=L: blend(c, L, hand_weights(L), fit_bias(c, L, tr)))

        def learned(tr, L=L):
            fac = fit_bias(c, L, tr)
            w, _ = fit_weights(c, L, tr, fac)
            return blend(c, L, w, fac)
        p["bias + learned w"] = oos(c, learned)

        def shrunk(tr, L=L):
            """Same, but the weights keep their fitted sum (< 1 at long leads: big forecasts are pulled back)."""
            fac = fit_bias(c, L, tr)
            w, scale = fit_weights(c, L, tr, fac)
            return blend(c, L, w, fac) * scale
        p["... + shrink"] = oos(c, shrunk)
        res.setdefault("shrink", []).append(round(fit_weights(c, L, np.ones(o.size, bool), fit_bias(c, L, np.ones(o.size, bool)))[1], 2))
        preds[L] = p
        fac = fit_bias(c, L, np.ones(o.size, bool))
        res["weights"][L] = {LABEL[m]: round(v, 2) for m, v in fit_weights(c, L, np.ones(o.size, bool), fac)[0].items()}
        for name, f in p.items():
            ok = np.isfinite(f) & np.isfinite(o)
            res["mae_wet"].setdefault(name, []).append(round(mae(f, o, wet), 2))
            res["mae_all"].setdefault(name, []).append(round(mae(f, o), 2))
            res["bias"].setdefault(name, []).append(round(float(f[ok].sum() / o[ok].sum()), 2))
        for new, old in (("hand (v2)", "NBM"), ("hand (v2)", "ECMWF"), ("bias-corrected", "hand (v2)"),
                         ("bias + learned w", "hand (v2)"), ("... + shrink", "hand (v2)"), ("bias + learned w", "NBM")):
            res["ci"].setdefault(f"{new} vs {old}", []).append(
                [round(100 * x, 1) for x in boot_diff(p[new], p[old], o, c["s"], wet)])
    # big days: 12.7 mm of water is roughly 6 in of snow
    big = o >= 12.7
    res["csi_big"] = {}
    for name in ("ECMWF", "NBM", "hand (v2)", "bias + learned w"):
        row = []
        for L in LEADS:
            f = preds[L][name]
            ok = np.isfinite(f)
            hit = (f[ok] >= 12.7) & big[ok]
            row.append(round(float(hit.sum() / max(((f[ok] >= 12.7) | big[ok]).sum(), 1)), 2))
        res["csi_big"][name] = row
    res["n_big"] = int(big.sum())
    res["n_days"] = int(np.isfinite(o).sum())
    res["n_wet"] = int(wet.sum())
    return res, preds


def exp_station_bias(c) -> dict:
    """Is the bias a stable property of the place? Station factors of winter 1 against winter 2."""
    out = {}
    for m in MODELS:
        f, o = c[f"{m}|1"], c["obs"]
        a, b = [], []
        for s in np.unique(c["s"]):
            r = []
            for w in (0, 1):
                ok = (c["s"] == s) & (c["w"] == w) & np.isfinite(f) & np.isfinite(o)
                r.append(o[ok].sum() / f[ok].sum() if f[ok].sum() > 50 else np.nan)
            a.append(r[0]); b.append(r[1])
        a, b = np.array(a), np.array(b)
        ok = np.isfinite(a) & np.isfinite(b)
        out[LABEL[m]] = {"corr": round(float(np.corrcoef(np.log(a[ok]), np.log(b[ok]))[0, 1]), 2),
                         "median": round(float(np.median(np.r_[a[ok], b[ok]])), 2),
                         "p10": round(float(np.percentile(np.r_[a[ok], b[ok]], 10)), 2),
                         "p90": round(float(np.percentile(np.r_[a[ok], b[ok]], 90)), 2),
                         "w1": [round(float(x), 2) for x in a], "w2": [round(float(x), 2) for x in b]}
    return out


def exp_sources(c) -> dict:
    """Data-source questions: (a) ECMWF at 9 km instead of 0.25 deg, (b) fewer models, as the standard tier has."""
    o, wet = c["obs"], c["obs"] >= WET_MM
    out = {"leads": list(LEADS), "ecmwf": {}, "subsets": {}}
    w2 = (c["w"] == 1) & np.isfinite(c["ecmwf_ifs|1"])
    for name, key in (("ECMWF 0.25 deg", "ecmwf_ifs025"), ("ECMWF 9 km", "ecmwf_ifs")):
        out["ecmwf"][name] = {
            "mae_wet": [round(mae(c[f"{key}|{L}"], o, wet & w2), 2) for L in LEADS],
            "bias": [round(float(np.nansum(np.where(w2, c[f"{key}|{L}"], np.nan))
                                 / o[w2 & np.isfinite(c[f"{key}|{L}"])].sum()), 2) for L in LEADS],
            "corr": [round(float(np.corrcoef(c[f"{key}|{L}"][k], o[k])[0, 1]), 2) if (k := w2 & np.isfinite(c[f"{key}|{L}"])).sum() > 100
                     else float("nan") for L in LEADS]}
    # the hand blend with ECMWF swapped for its 9 km version (same weights, winter 2025-26 only)
    swap = dict(c)
    for L in LEADS:
        swap[f"ecmwf_ifs025|{L}"] = c[f"ecmwf_ifs|{L}"]
    out["ecmwf"]["hand blend, 0.25 deg"] = {"mae_wet": [round(mae(blend(c, L, hand_weights(L)), o, wet & w2), 2) for L in LEADS]}
    out["ecmwf"]["hand blend, 9 km"] = {"mae_wet": [round(mae(blend(swap, L, hand_weights(L)), o, wet & w2), 2) for L in LEADS]}
    lo, hi = zip(*[boot_diff(blend(swap, L, hand_weights(L)), blend(c, L, hand_weights(L)), o, c["s"], wet & w2) for L in LEADS])
    out["ecmwf"]["blend change, 90 % interval (%)"] = [[round(100 * a, 1), round(100 * b, 1)] for a, b in zip(lo, hi)]
    # fewer models (both winters)
    for name, keep in (("all 5 models", MODELS), ("ECMWF + GFS + NBM (standard tier, US)", ("ecmwf_ifs025", "gfs_global", "ncep_nbm_conus")),
                       ("ECMWF + GFS (standard tier, no regional model)", ("ecmwf_ifs025", "gfs_global")),
                       ("ECMWF + GFS + ICON + GEM (no NBM)", ("ecmwf_ifs025", "gfs_global", "icon_global", "gem_global"))):
        row = []
        for L in LEADS:
            w = {m: (v if m in keep else 0.0) for m, v in hand_weights(L).items()}
            row.append(round(mae(blend(c, L, w), o, wet), 2))
        out["subsets"][name] = row
    return out


def exp_totals(c, preds) -> dict:
    """What bias correction is for: totals. (a) winter total per station, (b) 3-day totals from one issue time."""
    o = c["obs"]
    out = {"season_abs_err": {}, "three_day_mae": {}}
    for name in ("ECMWF", "NBM", "hand (v2)", "bias-corrected", "bias + learned w"):
        f = preds[1][name]
        errs = []
        for s in np.unique(c["s"]):
            for w in (0, 1):
                ok = (c["s"] == s) & (c["w"] == w) & np.isfinite(f) & np.isfinite(o)
                if o[ok].sum() > 100:
                    errs.append(abs(f[ok].sum() / o[ok].sum() - 1.0))
        out["season_abs_err"][name] = {"median": round(float(np.median(errs)), 3), "p90": round(float(np.percentile(errs, 90)), 3),
                                       "n": len(errs)}
    # 3-day total issued on day D-1: day D at lead 1, D+1 at lead 2, D+2 at lead 3
    idx = {(s, d): i for i, (s, d) in enumerate(zip(c["s"], c["date"]))}
    trip = []
    for i, (s, d) in enumerate(zip(c["s"], c["date"])):
        d0 = date.fromisoformat(d)
        j = idx.get((s, (d0 + timedelta(days=1)).isoformat()))
        k = idx.get((s, (d0 + timedelta(days=2)).isoformat()))
        if j is not None and k is not None:
            trip.append((i, j, k))
    i, j, k = (np.array(x) for x in zip(*trip))
    tot_o = o[i] + o[j] + o[k]
    wet3 = tot_o >= 7.6
    for name in ("ECMWF", "NBM", "hand (v2)", "bias-corrected", "bias + learned w"):
        tot_f = preds[1][name][i] + preds[2][name][j] + preds[3][name][k]
        out["three_day_mae"][name] = round(mae(tot_f, tot_o, wet3), 2)
    out["three_day_n"] = int(wet3.sum())
    out["three_day_mean_obs"] = round(float(tot_o[wet3].mean()), 1)
    return out


BINS = (0.0, 1.0, 5.0, 12.0, 25.0, 1e9)


def exp_bands(c, preds) -> dict:
    """Empirical error bands by lead and forecast size, against the 5-model min-max range."""
    o = c["obs"]
    res = {"leads": [L for L in LEADS if L], "coverage_empirical": [], "coverage_models": [], "width_empirical": [],
           "width_models": [], "fan": {}}
    for L in res["leads"]:
        f = preds[L]["bias + learned w"]
        lo, hi = np.full(o.size, np.nan), np.full(o.size, np.nan)
        for test_w in (0, 1):
            tr, te = c["w"] != test_w, c["w"] == test_w
            for b0, b1 in zip(BINS, BINS[1:]):
                a = tr & np.isfinite(f) & np.isfinite(o) & (f >= b0) & (f < b1)
                x = te & (f >= b0) & (f < b1)
                if a.sum() >= 30:
                    lo[x], hi[x] = np.percentile(o[a], 10), np.percentile(o[a], 90)
        X = np.stack([c[f"{m}|{L}"] for m in MODELS], axis=1)
        mlo, mhi = np.nanmin(X, axis=1), np.nanmax(X, axis=1)
        sig = np.isfinite(f) & np.isfinite(o) & np.isfinite(lo) & ((f >= WET_MM) | (o >= WET_MM))
        res["coverage_empirical"].append(round(float(((o >= lo) & (o <= hi))[sig].mean()), 3))
        res["coverage_models"].append(round(float(((o >= mlo) & (o <= mhi))[sig].mean()), 3))
        res["width_empirical"].append(round(float((hi - lo)[sig].mean()), 1))
        res["width_models"].append(round(float((mhi - mlo)[sig].mean()), 1))
        # the fan for a "15 mm of water" day (about 6 in of snow): observed 10/50/90 % given a forecast of 12-25 mm
        a = np.isfinite(f) & np.isfinite(o) & (f >= 12) & (f < 25)
        res["fan"][L] = {"n": int(a.sum()), "p10": round(float(np.percentile(o[a], 10)), 1),
                         "p50": round(float(np.percentile(o[a], 50)), 1), "p90": round(float(np.percentile(o[a], 90)), 1),
                         "mean_fc": round(float(f[a].mean()), 1)}
    return res


def exp_slr(c) -> dict:
    """Snow-to-liquid ratio: 24 h depth gain / pillow gain on clean snow days, predicted from the day-1 forecast."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    t = np.nanmean(np.stack([c["ecmwf_ifs025|t"], c["gfs_global|t"]]), axis=0)
    wind = np.nanmean(np.stack([c["ecmwf_ifs025|wind"], c["gfs_global|wind"]]), axis=0)
    ok = (c["swe"] >= 7.6) & (c["depth"] > 0) & np.isfinite(t) & np.isfinite(wind) & (c["tavg"] < 0.5)
    slr = np.where(ok, c["depth"] * 10.0 / np.maximum(c["swe"], 1e-6), np.nan)
    ok &= (slr >= 2) & (slr <= 30)
    X = np.stack([t, wind, c["elev"] / 1000.0, np.cos((c["month"] - 1) * np.pi / 6)], axis=1)
    pred = {"constant 10": np.full(slr.size, 10.0),
            "Kuchera + wind (v2)": kuchera_slr(t + 273.15) * wind_factor(wind * 1.3)}
    pred["train median"] = oos(c, lambda tr: np.full(slr.size, np.median(slr[tr & ok])))
    pred["linear (T, wind, elev, month)"] = oos(c, lambda tr: LinearRegression().fit(X[tr & ok], slr[tr & ok]).predict(np.nan_to_num(X)))
    pred["gradient boosting"] = oos(c, lambda tr: HistGradientBoostingRegressor(max_depth=3, max_iter=150, learning_rate=0.05,
                                                                                min_samples_leaf=20).fit(X[tr & ok], slr[tr & ok]).predict(np.nan_to_num(X)))
    out = {"n": int(ok.sum()), "obs_median": round(float(np.median(slr[ok])), 1), "methods": {}}
    for name, p in pred.items():
        out["methods"][name] = {"mae_slr": round(mae(p, slr, ok), 2),
                                "mae_depth_cm": round(mae(p * c["swe"] / 10.0, c["depth"], ok), 2),
                                "bias_slr": round(float((p[ok] - slr[ok]).mean()), 2)}
    return out


def exp_persistence(c, preds) -> dict:
    """Does yesterday's forecast error say anything about today's (same storm)?"""
    f, o = preds[1]["bias + learned w"], c["obs"]
    idx = {(s, d): i for i, (s, d) in enumerate(zip(c["s"], c["date"]))}
    a, b, pairs = [], [], []
    for i, (s, d) in enumerate(zip(c["s"], c["date"])):
        j = idx.get((s, (date.fromisoformat(d) - timedelta(days=1)).isoformat()))
        if j is None or not all(np.isfinite(x) for x in (f[i], o[i], f[j], o[j])):
            continue
        if min(f[i], f[j], o[j]) >= WET_MM:
            pairs.append((i, j))
            a.append(np.log((o[j] + 2) / (f[j] + 2)))
            b.append(np.log((o[i] + 2) / (f[i] + 2)))
    a, b = np.array(a), np.array(b)
    i = np.array([p[0] for p in pairs])
    out = {"n": len(pairs), "corr_log_ratio": round(float(np.corrcoef(a, b)[0, 1]), 2), "mae_plain": round(float(np.abs(f[i] - o[i]).mean()), 2)}
    for alpha in (0.25, 0.5):
        g = f[i] * np.clip(np.exp(alpha * a), 0.6, 1.6)
        out[f"mae_alpha_{alpha}"] = round(float(np.abs(g - o[i]).mean()), 2)
    return out


# --------------------------------------------------------------------------- report
def table(title, leads, d, fmt="%6.2f"):
    print(f"\n{title}")
    print("%-22s" % "" + "".join("%8s" % f"d+{L}" for L in leads))
    for k, v in d.items():
        print("%-22s" % k + "".join("%8s" % (fmt % x) for x in v))


def charts(res) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e6e3", "grid.linewidth": 0.8, "axes.edgecolor": "#b4b3ad", "figure.dpi": 150})
    p = res["precip"]
    leads = p["leads"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    # name -> (colour, width, dash, label, vertical label offset in points)
    style = {"GFS": ("#b4b3ad", 1.3, "-", "GFS", 6), "ICON": ("#b4b3ad", 1.3, "--", "ICON", 0), "GEM": ("#b4b3ad", 1.3, ":", "GEM", 0),
             "ECMWF": ("#6b6a66", 1.6, "-", "ECMWF", 0), "NBM": ("#6b6a66", 1.6, "--", "NBM", 7),
             "hand (v2)": ("#d9622b", 2.4, "-", "our blend today", -8),
             "bias + learned w": ("#2a78d6", 2.4, "-", "blend + corrections", 7 if False else -20)}
    for name, (col, lw, ls, label, dy) in style.items():
        y = p["mae_wet"][name]
        last = max(i for i, v in enumerate(y) if v == v)
        ax.plot(leads, y, color=col, lw=lw, ls=ls, marker="o", ms=3.5)
        ax.annotate(label, (leads[last], y[last]), xytext=(7, dy), textcoords="offset points", va="center", fontsize=9, color=col)
    ax.set_xlabel("lead time (days)"); ax.set_ylabel("mean absolute error on wet days (mm of water)")
    ax.set_title("Daily precipitation error at 29 SNOTEL stations, out of sample", loc="left", fontsize=11)
    ax.set_xticks(leads); ax.set_xlim(-0.2, 9.2)
    fig.tight_layout(); fig.savefig(RAW / "chart_mae_by_lead.png"); plt.close(fig)

    b = res["bands"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    L = b["leads"]
    lo = [b["fan"][x]["p10"] for x in L]; md = [b["fan"][x]["p50"] for x in L]; hi = [b["fan"][x]["p90"] for x in L]
    ax.fill_between(L, lo, hi, color="#2a78d6", alpha=0.25, label="10-90 % of what was observed")
    ax.plot(L, md, color="#2a78d6", lw=2.4, marker="o", ms=4, label="median observed")
    ax.plot(L, [b["fan"][x]["mean_fc"] for x in L], color="#6b6a66", lw=1.4, ls="--", label="mean forecast")
    ax.set_xlabel("lead time (days)"); ax.set_ylabel("observed precipitation (mm of water)")
    ax.set_title("When the forecast said 12-25 mm: what actually fell", loc="left", fontsize=11)
    ax.set_xticks(L); ax.set_ylim(0, None); ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout(); fig.savefig(RAW / "chart_fan_by_lead.png"); plt.close(fig)


def main() -> None:
    c = load()
    print(f"truth = {TRUTH}")
    print(f"{len(c['_stations'])} stations, {c['obs'].size} station-days, {(c['obs'] >= WET_MM).sum()} wet (>= {WET_MM} mm)")
    for m in MODELS:
        print("  %-6s available: %s" % (LABEL[m], {L: int(np.isfinite(c[f'{m}|{L}']).sum()) for L in LEADS}))
    for m, L in sorted(BROKEN):
        x = c[f"raw|{m}|{L}"]
        ok = np.isfinite(x)
        print(f"  excluded {LABEL[m]} d+{L}: archive total / observed = {x[ok].sum() / c['obs'][ok].sum():.2f}")
    r = {LABEL[m]: [round(float(np.corrcoef(c[f'{m}|{L}'][k], c['obs'][k])[0, 1]), 2) if (k := np.isfinite(c[f'{m}|{L}'])).sum() > 100 else float('nan')
                    for L in LEADS] for m in MODELS}
    table("Correlation of daily forecast with observation", LEADS, r)
    precip, preds = exp_precip(c)
    table("MAE on wet days (mm), out of sample", LEADS, precip["mae_wet"])
    table("MAE on all days (mm)", LEADS, precip["mae_all"])
    table("Bias (sum forecast / sum observed)", LEADS, precip["bias"])
    print("\nLearned weights (all data):")
    for L, w in precip["weights"].items():
        print(f"  d+{L}: {w}")
    print("\nRelative MAE change on wet days, 90 % interval over stations (negative = better):")
    for k, v in precip["ci"].items():
        print("  %-34s" % k + "  ".join(f"d+{L}: {a:+.0f}..{b:+.0f}%" for L, (a, b) in zip(LEADS, v)))
    table("CSI for days with >= 12.7 mm of water (about 6 in of snow)", LEADS, precip["csi_big"])
    print("fitted sum of weights (1 = no shrinking):", dict(zip(LEADS, precip["shrink"])))
    src = exp_sources(c)
    print("\nECMWF 9 km against 0.25 deg (winter 2025-26 only):")
    for k, v in src["ecmwf"].items():
        print("  %-22s %s" % (k, v))
    table("Fewer models: MAE on wet days (mm), hand weights", LEADS, src["subsets"])
    res = {"truth": TRUTH, "precip": precip, "sources": src, "totals": exp_totals(c, preds), "station_bias": exp_station_bias(c), "bands": exp_bands(c, preds), "slr": exp_slr(c),
           "persistence": exp_persistence(c, preds)}
    print("\nStation bias factors, winter 1 against winter 2 (lead 1):")
    for k, v in res["station_bias"].items():
        print(f"  {k:6s} corr {v['corr']:+.2f}  median {v['median']:.2f}  10-90 %: {v['p10']:.2f}-{v['p90']:.2f}")
    print("\nTotals:", json.dumps(res["totals"], indent=1))
    b = res["bands"]
    print("\nRange check on wet days (target coverage 0.80):")
    print("  lead        " + "".join("%8s" % f"d+{L}" for L in b["leads"]))
    for k in ("coverage_empirical", "coverage_models", "width_empirical", "width_models"):
        print("  %-20s" % k + "".join("%8s" % x for x in b[k]))
    print("  fan for a 12-25 mm forecast:", b["fan"])
    print("\nSLR:", json.dumps(res["slr"], indent=1))
    print("\nPersistence of the error within a storm:", res["persistence"])
    (RAW / f"results_{TRUTH}.json").write_text(json.dumps(res, indent=1))
    if TRUTH == "gauge":
        charts(res)


if __name__ == "__main__":
    main()
