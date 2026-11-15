"""Is the Powder Planner worth building? Decision-value backtest on the phase-3 data set.

    python scripts/research/planner_backtest.py

Same data as analyze_backtest.py (29 SNOTEL stations, two winters). The planner's input is the
blend with the production hand weights, exactly as it would have been issued L days ahead.
A "powder day" is a day with >= 12.7 mm of water (about 6 in of snow) and a mean temperature <= 0.5 C.

Every rule that needs a number learned from data (thresholds, probabilities, "snowiest mountain")
takes it from the other winter.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_backtest as ab  # noqa: E402

LEADS = (1, 2, 3, 5, 7)
BIG = 12.7
GROUPS = {"Tahoe": "tahoe", "Utah": "utah", "Colorado": "colorado", "Cascades": "pnw", "N. Rockies": "northern-rockies"}
DAYS_PER_SEASON = 10


def cube(c):
    """(winter, station, day) arrays."""
    stations = sorted(set(c["s"].tolist()))
    out = {}
    for w in (0, 1):
        dates = sorted(set(c["date"][c["w"] == w].tolist()))
        di = {d: i for i, d in enumerate(dates)}
        shape = (len(stations), len(dates))
        a = {"dates": dates, "obs": np.full(shape, np.nan), "cold": np.zeros(shape, bool),
             "dow": np.array([date.fromisoformat(d).weekday() for d in dates])}
        F = {name: {L: np.full(shape, np.nan) for L in LEADS} for name in ("blend", "NBM", "ECMWF", "blend, cold only")}
        fc = {"blend": {L: ab.blend(c, L, ab.hand_weights(L)) for L in LEADS},
              "NBM": {L: c[f"ncep_nbm_conus|{L}"] for L in LEADS}, "ECMWF": {L: c[f"ecmwf_ifs025|{L}"] for L in LEADS}}
        # forecast temperature (mean of the models, issued one day ahead, at station height): precipitation on a
        # day forecast warmer than 0.5 C does not count as snow. Only lead 1 is clean, the archive has no other lead.
        tfc = np.nanmean(np.stack([c[f"{m}|t"] for m in ab.MODELS]), axis=0)
        fc["blend, cold only"] = {L: np.where(tfc <= 0.5, fc["blend"][L], 0.0) for L in LEADS}
        for i in np.flatnonzero(c["w"] == w):
            s, d = int(c["s"][i]), di[c["date"][i]]
            a["obs"][s, d] = c["obs"][i]
            a["cold"][s, d] = not (c["tavg"][i] > 0.5)
            for name in F:
                for L in LEADS:
                    F[name][L][s, d] = fc[name][L][i]
        a["F"] = F
        a["powder"] = (a["obs"] >= BIG) & a["cold"]
        a["big"] = a["obs"] >= BIG                      # same amount, rain or snow
        out[w] = a
    region = np.array([c["_stations"][s]["region"] for s in stations])
    return out, region


def r(x, n=1):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


# --------------------------------------------------------------------------- E1: which day (home mountain)
def which_day(cb, source="blend"):
    """Go when the forecast is in the top-10-days-a-season range (threshold from the other winter)."""
    res = {}
    for L in LEADS:
        n_go, got, hit, caught, total_powder, base, oracle, seasons = 0, 0.0, 0, 0, 0, [], [], 0
        for w in (0, 1):
            a, b = cb[w], cb[1 - w]
            for s in range(a["obs"].shape[0]):
                f_tr = b["F"][source][L][s]
                f, o = a["F"][source][L][s], a["obs"][s]
                ok = np.isfinite(f) & np.isfinite(o)
                if np.isfinite(f_tr).sum() < 100 or ok.sum() < 100:
                    continue
                thr = np.nanquantile(f_tr, 1 - DAYS_PER_SEASON / np.isfinite(f_tr).sum())
                go = ok & (f >= thr)
                seasons += 1
                n_go += go.sum(); got += o[go].sum(); hit += a["powder"][s][go].sum()
                caught += a["powder"][s][go].sum(); total_powder += a["powder"][s][ok].sum()
                base.append(o[ok].mean()); oracle.append(np.sort(o[ok])[-DAYS_PER_SEASON:].mean())
        res[L] = {"days_per_season": r(n_go / seasons), "mm_per_ski_day": r(got / n_go), "powder_share_of_ski_days": r(hit / n_go, 2),
                  "powder_days_caught_share": r(caught / total_powder, 2), "random_day_mm": r(np.mean(base)),
                  "oracle_mm": r(np.mean(oracle)), "powder_days_per_season": r(total_powder / seasons)}
    return res


# --------------------------------------------------------------------------- E2: which mountain (fixed day)
def which_mountain(cb, region, source="blend"):
    res = {}
    for L in LEADS:
        tot = {"picked": [], "mean": [], "best": [], "snowiest": [], "is_best": [], "picked_powder": [], "snowiest_powder": []}
        for w in (0, 1):
            a, b = cb[w], cb[1 - w]
            for reg in GROUPS.values():
                idx = np.flatnonzero(region == reg)
                o, f = a["obs"][idx], a["F"][source][L][idx]
                clim = int(np.nanargmax(np.nansum(b["obs"][idx], axis=1)))      # snowiest last winter
                for d in range(o.shape[1]):
                    if not (np.isfinite(o[:, d]).all() and np.isfinite(f[:, d]).all()):
                        continue
                    if o[:, d].max() < BIG:                                      # no storm: the choice does not matter
                        continue
                    k = int(np.argmax(f[:, d]))
                    tot["picked"].append(o[k, d]); tot["mean"].append(o[:, d].mean()); tot["best"].append(o[:, d].max())
                    tot["snowiest"].append(o[clim, d]); tot["is_best"].append(o[k, d] >= o[:, d].max() - 1e-9)
                    tot["picked_powder"].append(a["powder"][idx[k], d]); tot["snowiest_powder"].append(a["powder"][idx[clim], d])
        m = {k: float(np.mean(v)) for k, v in tot.items()}
        res[L] = {"n_storm_days": len(tot["picked"]), "picked_mm": r(m["picked"]), "average_mountain_mm": r(m["mean"]),
                  "always_snowiest_mm": r(m["snowiest"]), "best_possible_mm": r(m["best"]),
                  "capture_vs_average": r((m["picked"] - m["mean"]) / (m["best"] - m["mean"]), 2),
                  "picked_is_best": r(m["is_best"], 2), "picked_gets_powder": r(m["picked_powder"], 2),
                  "snowiest_gets_powder": r(m["snowiest_powder"], 2)}
    return res


# --------------------------------------------------------------------------- E3/E4: weekend skier in a region
def weekend(cb, region, source="blend", L=2):
    """Each weekend one outing. Planner: best (mountain, day) by the forecast. Habit: Saturday at the snowiest mountain."""
    got = {"planner": [], "home_pick_day": [], "habit": [], "random": [], "best": []}
    pw = {"planner": [], "home_pick_day": [], "habit": []}
    for w in (0, 1):
        a, b = cb[w], cb[1 - w]
        sat = np.flatnonzero(a["dow"] == 5)
        for reg in GROUPS.values():
            idx = np.flatnonzero(region == reg)
            clim = int(np.nanargmax(np.nansum(b["obs"][idx], axis=1)))
            for d in sat:
                if d + 1 >= a["obs"].shape[1]:
                    continue
                o, f = a["obs"][idx][:, d:d + 2], a["F"][source][L][idx][:, d:d + 2]
                if not (np.isfinite(o).all() and np.isfinite(f).all()):
                    continue
                k = np.unravel_index(int(np.argmax(f)), f.shape)
                j = int(np.argmax(f[clim]))                      # stay at the home mountain, only choose Saturday or Sunday
                got["planner"].append(o[k]); got["habit"].append(o[clim, 0]); got["random"].append(o.mean()); got["best"].append(o.max())
                got["home_pick_day"].append(o[clim, j])
                pw["planner"].append(a["powder"][idx[k[0]], d + k[1]]); pw["habit"].append(a["powder"][idx[clim], d])
                pw["home_pick_day"].append(a["powder"][idx[clim], d + j])
    n = len(got["planner"])
    return {"weekends": n, "lead_days": L,
            **{f"{k}_mm": r(np.mean(v)) for k, v in got.items()},
            **{f"{k}_powder_per_20_weekends": r(20 * np.mean(v)) for k, v in pw.items()}}


# --------------------------------------------------------------------------- E5: probability of a powder day, go / wait
EDGES = (0.0, 2.5, 7.5, 12.5, 20.0, 30.0, 1e9)


def probability(cb, source="blend", key="powder"):
    res = {}
    for L in LEADS:
        p_all, y_all = [], []
        for w in (0, 1):
            a, b = cb[w], cb[1 - w]
            f_tr, y_tr = b["F"][source][L].ravel(), b[key].ravel()
            ok_tr = np.isfinite(f_tr) & np.isfinite(b["obs"].ravel())
            table = [y_tr[ok_tr & (f_tr >= lo) & (f_tr < hi)].mean() if (ok_tr & (f_tr >= lo) & (f_tr < hi)).sum() >= 20 else np.nan
                     for lo, hi in zip(EDGES, EDGES[1:])]
            f, y = a["F"][source][L].ravel(), a[key].ravel()
            ok = np.isfinite(f) & np.isfinite(a["obs"].ravel())
            p = np.array(table)[np.clip(np.searchsorted(EDGES, f[ok], side="right") - 1, 0, len(table) - 1)]
            keep = np.isfinite(p)
            p_all.append(p[keep]); y_all.append(y[ok][keep])
        p, y = np.concatenate(p_all), np.concatenate(y_all).astype(float)
        base = y.mean()
        bss = 1 - np.mean((p - y) ** 2) / np.mean((base - y) ** 2)
        rel = []
        for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)):
            m = (p >= lo) & (p < hi)
            rel.append({"said": r(p[m].mean(), 2) if m.any() else None, "happened": r(y[m].mean(), 2) if m.any() else None, "n": int(m.sum())})
        rule = {}
        for thr in (0.5, 0.7):
            go = p >= thr
            rule[f"go_at_{thr}"] = {"calls": int(go.sum()), "right": r(y[go].mean(), 2) if go.any() else None,
                                    "powder_days_flagged": r(y[go].sum() / y.sum(), 2)}
        res[L] = {"base_rate": r(base, 3), "brier_skill": r(bss, 2), "reliability": rel, **rule}
    return res


# --------------------------------------------------------------------------- E6: fly-in trip, which region
def trip(cb, region, source="blend"):
    """A 3-day trip starting on day D. Region score at booking time against what the region then got (mean of its stations)."""
    res = {}
    plans = {"book 5 days ahead": ((5, 0), (7, 2)), "book the day before": ((1, 0), (2, 1), (3, 2))}
    for name, parts in plans.items():
        got = {"picked": [], "mean": [], "best": [], "snowiest": []}
        for w in (0, 1):
            a, b = cb[w], cb[1 - w]
            regs = list(GROUPS.values())
            O = np.stack([np.nanmean(a["obs"][region == g], axis=0) for g in regs])
            Fm = {L: np.stack([np.nanmean(a["F"][source][L][region == g], axis=0) for g in regs]) for L in LEADS}
            clim = int(np.argmax([np.nansum(b["obs"][region == g]) / (region == g).sum() for g in regs]))
            n = O.shape[1]
            for d in range(0, n - 2):
                tot = O[:, d] + O[:, d + 1] + O[:, d + 2]
                score = sum(Fm[L][:, d + off] for L, off in parts)
                if not (np.isfinite(tot).all() and np.isfinite(score).all()):
                    continue
                if tot.max() < 30:                # only weeks in which a trip somewhere was worth it
                    continue
                k = int(np.argmax(score))
                got["picked"].append(tot[k]); got["mean"].append(tot.mean()); got["best"].append(tot.max()); got["snowiest"].append(tot[clim])
        m = {k: float(np.mean(v)) for k, v in got.items()}
        res[name] = {"n_windows": len(got["picked"]), "picked_mm": r(m["picked"]), "average_region_mm": r(m["mean"]),
                     "always_snowiest_region_mm": r(m["snowiest"]), "best_possible_mm": r(m["best"]),
                     "capture_vs_average": r((m["picked"] - m["mean"]) / (m["best"] - m["mean"]), 2)}
    return res


def charts(out) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e6e3", "grid.linewidth": 0.8, "axes.edgecolor": "#b4b3ad", "figure.dpi": 150})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 4.0), gridspec_kw={"width_ratios": [1, 1.25]})
    w = out["weekend"]["lead 2"]
    names = ["Saturday at the\nusual mountain", "usual mountain,\nbetter day", "planner: best\nmountain and day"]
    vals = [w["habit_powder_per_20_weekends"], w["home_pick_day_powder_per_20_weekends"], w["planner_powder_per_20_weekends"]]
    bars = a1.bar(names, vals, color=["#b4b3ad", "#86b6ef", "#2a78d6"], width=0.62)
    for b_, v in zip(bars, vals):
        a1.text(b_.get_x() + b_.get_width() / 2, v + 0.08, f"{v:.1f}", ha="center", va="bottom", fontsize=11, fontweight="bold")
    a1.set_ylabel("powder weekends out of 20"); a1.grid(axis="x", visible=False)
    a1.set_title("Weekend skier, decided 2 days ahead", loc="left", fontsize=11); a1.tick_params(axis="x", labelsize=9)
    L = list(LEADS)
    day = out["which_day"]["blend"]
    a2.plot(L, [100 * day[x]["powder_share_of_ski_days"] for x in L], color="#2a78d6", lw=2.4, marker="o", ms=4)
    a2.annotate("days the planner picked", (L[-1], 100 * day[7]["powder_share_of_ski_days"]), xytext=(-4, 12), textcoords="offset points",
                ha="right", fontsize=9, color="#2a78d6")
    base = 100 * out["probability"][1]["base_rate"]
    a2.axhline(base, color="#6b6a66", lw=1.4, ls="--")
    a2.annotate("any day", (L[-1], base), xytext=(-4, 5), textcoords="offset points", ha="right", fontsize=9, color="#6b6a66")
    a2.set_xticks(L); a2.set_ylim(0, 70); a2.set_xlabel("decided this many days ahead"); a2.set_ylabel("share that were powder days (%)")
    a2.set_title("Skiing about 11 days a season at one mountain", loc="left", fontsize=11)
    fig.tight_layout(); fig.savefig(ab.RAW / "chart_planner_value.png"); plt.close(fig)


def main() -> None:
    c = ab.load()
    cb, region = cube(c)
    out = {"which_day": {src: which_day(cb, src) for src in ("blend", "NBM")},
           "which_mountain": {src: which_mountain(cb, region, src) for src in ("blend", "NBM")},
           "weekend": {f"lead {L}": weekend(cb, region, "blend", L) for L in (1, 2, 3, 5)},
           "probability": probability(cb), "probability_any_precip_type": probability(cb, key="big"),
           "probability_with_forecast_temperature": {1: probability(cb, "blend, cold only")[1]},
           "which_day_with_forecast_temperature": {1: which_day(cb, "blend, cold only")[1]},
           "weekend_with_forecast_temperature": weekend(cb, region, "blend, cold only", 1), "trip": trip(cb, region)}
    print(json.dumps(out, indent=1))
    (ab.RAW / "results_planner.json").write_text(json.dumps(out, indent=1))
    charts(out)


if __name__ == "__main__":
    main()
