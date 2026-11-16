"""Scores of the archived forecasts against the archived observations (design doc A3).

    verification.json   windows "30d" (last 30 complete ski days) and "season" (since 1 Sep), each
                        with "overall", "regions" and "resorts"; every group is scored per lead time.

Pairs: for each (resort, ski day, lead) the LAST forecast issued with that lead (featured resorts
are issued up to four times a day), against the best grade A or B station of the resort (rank order
of data/stations.yaml). Grade C stations are not scored.

Per lead (days ahead in the resort's time zone when the forecast was issued):
    snow_mae_cm / snow_bias_cm     mid-mountain ski-day snowfall vs the station's new snow. The
                                   observation is a lower bound (settling), so a positive bias is
                                   expected; days flagged depth_fell are skipped.
    precip_mae_mm / precip_bias_mm liquid precipitation vs the gauge (which under-catches in wind).
    big                            days with >= 15 cm observed or forecast: hits, misses, false
                                   alarms, CSI = hits / (hits + misses + false alarms).
    brier_15, brier_2_5            Brier score of the ensemble's probability of >= 15 / >= 2.5 cm.
    coverage                       share of observations inside the published range (low-high) and
                                   inside the ensemble 10-90 % (target 80 %).
    models                         MAE of each raw model on the same pairs; skill_vs_nbm =
                                   1 - our MAE / NBM's MAE where NBM was in the blend.
Reliability of the 15 cm probability is kept for "overall" only (10 bins).
"recent": every observed ski day of the last 30 days that has a forecast made 1 or 3 days ahead.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from ..config import SCHEMA_VERSION
from .archive import METHOD, read_obs, read_rows

POINT_LEADS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
PROB_LEADS = tuple(range(16))
REPORT_LEADS = (1, 2, 3, 5, 7, 10)
BIG_CM = 15.0
SMALL_CM = 2.5
SCORED_GRADES = ("A", "B")
NBM = "ncep_nbm_conus"


def season_start(d: date) -> date:
    return date(d.year if d.month >= 9 else d.year - 1, 9, 1)


def latest_forecasts(rows: Iterable[dict]) -> dict[tuple, dict]:
    """(resort, target_date, lead) -> the last row issued for it."""
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (r["resort_id"], r["target_date"], r["lead_days"])
        if k not in out or r["issued_at"] > out[k]["issued_at"]:
            out[k] = r
    return out


def best_obs(rows: Iterable[dict]) -> dict[tuple, dict]:
    """(resort, ski day) -> the observation of the best scored station that has data."""
    out: dict[tuple, dict] = {}
    for r in rows:
        if r.get("grade") not in SCORED_GRADES:
            continue
        if r.get("precip_mm") is None and r.get("snow_cm") is None:
            continue
        k = (r["resort_id"], r["target_date"])
        if k not in out or r["rank"] < out[k]["rank"]:
            out[k] = r
    return out


def _mid(x) -> Optional[float]:
    if isinstance(x, dict):
        x = x.get("mid")
    return float(x) if isinstance(x, (int, float)) else None


class Acc:
    """Running sums for one (group, lead)."""

    def __init__(self) -> None:
        self.s = defaultdict(float)
        self.models: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])   # n, |err| model, |err| ours

    def add(self, f: dict, o: dict) -> None:
        s = self.s
        obs_snow = o.get("snow_cm") if "depth_fell" not in (o.get("flags") or []) else None
        ens = f.get("ens") or {}
        if f.get("kind") == "point":
            fs, op = _mid(f.get("snow_cm")), o.get("precip_mm")
            if fs is not None and obs_snow is not None:
                s["snow_n"] += 1
                s["snow_abs"] += abs(fs - obs_snow)
                s["snow_err"] += fs - obs_snow
                fb, ob = fs >= BIG_CM, obs_snow >= BIG_CM
                s["hits"] += fb and ob
                s["misses"] += ob and not fb
                s["false_alarms"] += fb and not ob
                lo, hi = _mid(f.get("snow_low_cm")), _mid(f.get("snow_high_cm"))
                if lo is not None and hi is not None:
                    s["cov_n"] += 1
                    s["cov_in"] += lo <= obs_snow <= hi
                if ens.get("p10") is not None and ens.get("p90") is not None:
                    s["ens_cov_n"] += 1
                    s["ens_cov_in"] += ens["p10"] <= obs_snow <= ens["p90"]
                for m, v in (f.get("by_model") or {}).items():
                    if isinstance(v, (int, float)):
                        a = self.models[m]
                        a[0] += 1
                        a[1] += abs(v - obs_snow)
                        a[2] += abs(fs - obs_snow)
            fp = f.get("precip_mm")
            if fp is not None and op is not None:
                s["precip_n"] += 1
                s["precip_abs"] += abs(fp - op)
                s["precip_err"] += fp - op
        if obs_snow is not None:
            for key, thr in (("15", BIG_CM), ("2_5", SMALL_CM)):
                p = ens.get(f"p_{key}")
                if p is not None:
                    s[f"brier_{key}_n"] += 1
                    s[f"brier_{key}"] += (p - (obs_snow >= thr)) ** 2

    def result(self) -> dict:
        s = self.s
        r = lambda x, nd=1: round(x, nd)  # noqa: E731
        out: dict = {"n": int(max(s["snow_n"], s["precip_n"], s["brier_15_n"]))}
        if s["snow_n"]:
            out["snow_mae_cm"] = r(s["snow_abs"] / s["snow_n"])
            out["snow_bias_cm"] = r(s["snow_err"] / s["snow_n"])
            out["snow_n"] = int(s["snow_n"])
            h, m, fa = s["hits"], s["misses"], s["false_alarms"]
            out["big"] = {"hits": int(h), "misses": int(m), "false_alarms": int(fa),
                          "csi": r(h / (h + m + fa), 3) if h + m + fa else None}
        if s["precip_n"]:
            out["precip_mae_mm"] = r(s["precip_abs"] / s["precip_n"])
            out["precip_bias_mm"] = r(s["precip_err"] / s["precip_n"])
            out["precip_n"] = int(s["precip_n"])
        for key in ("15", "2_5"):
            if s[f"brier_{key}_n"]:
                out[f"brier_{key}"] = r(s[f"brier_{key}"] / s[f"brier_{key}_n"], 4)
        cov = {}
        if s["cov_n"]:
            cov["range"] = r(s["cov_in"] / s["cov_n"], 3)
        if s["ens_cov_n"]:
            cov["ensemble_10_90"] = r(s["ens_cov_in"] / s["ens_cov_n"], 3)
        if cov:
            out["coverage"] = cov
        if self.models:
            out["models"] = {m: {"n": int(a[0]), "snow_mae_cm": r(a[1] / a[0]), "ours_snow_mae_cm": r(a[2] / a[0])}
                             for m, a in sorted(self.models.items()) if a[0]}
            nbm = self.models.get(NBM)
            if nbm and nbm[0] and nbm[1] > 0:
                out["skill_vs_nbm"] = r(1.0 - nbm[2] / nbm[1], 3)
        return out


def _reliability(pairs: list[tuple[float, bool]]) -> list[dict]:
    bins = [[0, 0.0, 0] for _ in range(10)]          # n, sum p, n observed
    for p, y in pairs:
        b = bins[min(9, int(p * 10))]
        b[0] += 1
        b[1] += p
        b[2] += y
    return [{"bin": f"{i * 10}-{i * 10 + 10}%", "n": n, "forecast": round(sp / n, 3), "observed": round(no / n, 3)}
            for i, (n, sp, no) in enumerate(bins) if n]


def score(forecasts: dict[tuple, dict], obs: dict[tuple, dict], region_of: dict[str, str],
          start: date, end: date) -> dict:
    groups: dict[tuple, Acc] = defaultdict(Acc)       # (kind, id, lead)
    rel: list[tuple[float, bool]] = []
    days, resorts = set(), set()
    for (rid, day, lead), f in forecasts.items():
        if not (start.isoformat() <= day <= end.isoformat()):
            continue
        o = obs.get((rid, day))
        if o is None:
            continue
        days.add(day)
        resorts.add(rid)
        for g in (("overall", ""), ("regions", region_of.get(rid, "?")), ("resorts", rid)):
            groups[(g[0], g[1], lead)].add(f, o)
        p = (f.get("ens") or {}).get("p_15")
        if p is not None and o.get("snow_cm") is not None and "depth_fell" not in (o.get("flags") or []):
            rel.append((p, o["snow_cm"] >= BIG_CM))

    def leads(kind: str, gid: str) -> dict:
        return {str(k): groups[(kind, gid, k)].result() for k in REPORT_LEADS if (kind, gid, k) in groups}

    ids = defaultdict(set)
    for kind, gid, _ in groups:
        ids[kind].add(gid)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "ski_days": len(days), "n_resorts": len(resorts),
        "overall": {"leads": leads("overall", ""), "reliability_15": _reliability(rel)},
        "regions": {g: {"leads": leads("regions", g)} for g in sorted(ids["regions"])},
        "resorts": {g: {"leads": leads("resorts", g)} for g in sorted(ids["resorts"])},
    }


RECENT_LEADS = (1, 3)


def recent_pairs(forecasts: dict[tuple, dict], obs: dict[tuple, dict], start: date, end: date) -> list[dict]:
    """Forecast vs observed per resort and ski day (for the page's day-by-day table)."""
    out = []
    for (rid, day), o in sorted(obs.items()):
        if not (start.isoformat() <= day <= end.isoformat()):
            continue
        fc = {}
        for k in RECENT_LEADS:
            f = forecasts.get((rid, day, k))
            if f and f.get("kind") == "point":
                fc[str(k)] = {"snow_cm": _mid(f.get("snow_cm")), "low_cm": _mid(f.get("snow_low_cm")),
                              "high_cm": _mid(f.get("snow_high_cm")), "precip_mm": f.get("precip_mm"),
                              "p_15": (f.get("ens") or {}).get("p_15")}
        if not fc:
            continue                                   # e.g. days before the archive started
        out.append({"resort_id": rid, "date": day, "station": o.get("station"), "obs_snow_cm": o.get("snow_cm"),
                    "obs_precip_mm": o.get("precip_mm"), "flags": o.get("flags") or [], "forecast": fc})
    return out


def build_verification(root: Path | str, region_of: dict[str, str], now: datetime) -> dict:
    """verification.json from the archive directory (forecasts/ and obs/)."""
    today = now.astimezone(timezone.utc).date()
    end = today - timedelta(days=1)                   # the last ski day that has ended everywhere
    s_start = season_start(end)
    want = set(region_of)
    obs = best_obs(read_obs(root, s_start, end))
    with_obs = {rid for rid, _ in obs} & want
    fc = latest_forecasts(r for r in read_rows(root, with_obs, s_start - timedelta(days=16), end)
                          if s_start.isoformat() <= r["target_date"] <= end.isoformat())
    w30 = max(s_start, end - timedelta(days=29))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": METHOD,
        "observations": "USDA NRCS SNOTEL (US) and SLF IMIS (Switzerland and nearby), best grade A/B station per resort (data/stations.yaml)",
        "units": {"snow": "cm", "precip": "mm"},
        "leads": list(REPORT_LEADS),
        "notes": "Observed new snow is a lower bound (settling), gauge precipitation under-catches in wind. "
                 "Definitions: pipeline/verify/score.py.",
        "windows": {
            "30d": score(fc, obs, region_of, w30, end),
            "season": score(fc, obs, region_of, s_start, end),
        },
        "recent": recent_pairs(fc, obs, w30, end),
    }
