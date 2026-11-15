"""Calendar feeds of powder days (design doc B6): alerts without an account or a backend.

    ics/{lang}/{pass}/{area}.ics     lang: en | zh; pass: all | ikon | epic;
                                     area: all | g-{group} (data/region_groups.yaml) | {region}

One all-day event per (resort, ski day) that is a likely powder day: at most 4 days ahead (the
planner backtest: picking a mountain further out does not pay off), powder score >= 60 and a
>= 60 % chance of 15 cm (6 in) or more. Calendar apps re-read a subscribed feed every few hours;
an event whose forecast drops below the bar disappears, one that changes keeps its UID.
The data is planner.json (pipeline/publish/planner.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import yaml

MIN_SCORE = 60
MIN_P15 = 0.6
MAX_AHEAD = 4
LIFTS_CLOSE_H = 16
SITE = "https://tokenfly.ai/snow"
GROUPS_FILE = Path(__file__).resolve().parents[2] / "data" / "region_groups.yaml"
PASSES = ("all", "ikon", "epic")
LANGS = ("en", "zh")


def load_groups(path: Path | str = GROUPS_FILE) -> list[dict]:
    return (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("groups") or []


def areas(region_ids: Iterable[str], groups: list[dict]) -> dict[str, set[str]]:
    """area slug -> regions."""
    regions = set(region_ids)
    out = {"all": regions}
    out.update({f"g-{g['id']}": set(g["regions"]) & regions for g in groups})
    out.update({r: {r} for r in regions})
    return out


# ---- iCalendar text ------------------------------------------------------------------------------

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """RFC 5545: lines of at most 75 octets, continued with CRLF + space (never inside a UTF-8 character)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _inch(cm: Optional[float]) -> str:
    if cm is None:
        return "–"
    return "0″" if cm < 0.1 else f"{cm / 2.54:.0f}″" if cm >= 2.54 else f"{cm / 2.54:.1f}″"


def _cm(cm: Optional[float]) -> str:
    return "–" if cm is None else f"{cm:.0f}"


def event_text(lang: str, m: dict, d: dict) -> tuple[str, str]:
    """(summary, description) of one powder day."""
    name = (m.get("name_zh") or m["name"]) if lang == "zh" else m["name"]
    fresh, night, cm, lo, hi = d["fresh"], d["night"], d["cm"], d["low"], d["high"]
    p15 = round(100 * (d["p15"] or 0))
    url = f"{SITE}/resort/{m['id']}/"
    if lang == "zh":
        lines = [f"开门时新雪：{_cm(fresh)} 厘米（其中夜间 {_cm(night)} 厘米）",
                 f"全天降雪：{_cm(cm)} 厘米（范围 {_cm(lo)}–{_cm(hi)}）",
                 f"≥ 15 厘米的概率：{p15}%"]
        if d.get("quality") == "powder":
            lines.append("雪质：粉雪")
        elif d.get("quality") == "heavy":
            lines.append("雪质：湿重")
        if (d.get("gust") or 0) > 70:
            lines.append(f"山顶阵风最大 {d['gust']:.0f} 公里/小时，缆车可能停")
        if d.get("rain_mid"):
            lines.append("山腰可能下雨")
        lines += [f"粉雪分 {d['score']}", "这是预报，不是保证：出发前看雪场的雪报。", url]
        return f"粉雪日：{name}，开门新雪 {_cm(fresh)} 厘米", "\n".join(lines)
    lines = [f"Fresh at opening: {_inch(fresh)} ({_cm(fresh)} cm), {_inch(night)} of it overnight",
             f"Ski-day total: {_inch(cm)} (range {_inch(lo)}–{_inch(hi)})",
             f"Chance of 6″+: {p15}%"]
    if d.get("quality") in ("powder", "heavy"):
        lines.append(f"Snow: {'powder' if d['quality'] == 'powder' else 'heavy'}")
    if (d.get("gust") or 0) > 70:
        lines.append(f"Summit gusts up to {d['gust'] / 1.609:.0f} mph: lifts may hold")
    if d.get("rain_mid"):
        lines.append("Rain possible at mid-mountain")
    lines += [f"Powder score {d['score']}", "A forecast, not a promise: check the resort's report before you go.", url]
    return f"Powder day: {name}, {_inch(fresh)} fresh", "\n".join(lines)


def powder_days(planner: dict, now: datetime) -> list[tuple[str, dict, dict]]:
    """(resort id, resort meta, day) of every day that clears the bar, soonest first."""
    fields = planner["fields"]
    out = []
    for rid, r in planner["resorts"].items():
        local = now.astimezone(ZoneInfo(r["timezone"]))
        today = local.date() + timedelta(days=1 if local.hour >= LIFTS_CLOSE_H else 0)
        for row in r["days"]:
            d = dict(zip(fields, row))
            ahead = (date.fromisoformat(d["date"]) - today).days
            if 0 <= ahead <= MAX_AHEAD and d["score"] >= MIN_SCORE and (d["p15"] or 0) >= MIN_P15:
                out.append((rid, {**r, "id": rid}, d))
    out.sort(key=lambda x: (x[2]["date"], -x[2]["score"]))
    return out


def calendar(lang: str, title: str, events: list[tuple[str, dict, dict]], now: datetime) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tokenfly.ai//Snow Powder Planner//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(title)}",
             f"X-WR-CALDESC:{esc('粉雪日提醒（tokenfly.ai/snow）' if lang == 'zh' else 'Likely powder days from tokenfly.ai/snow')}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for rid, m, d in events:
        day = date.fromisoformat(d["date"])
        summary, desc = event_text(lang, m, d)
        lines += ["BEGIN:VEVENT", f"UID:{rid}-{d['date']}@snow.tokenfly.ai", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}",
                  f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{esc(summary)}", f"DESCRIPTION:{esc(desc)}", f"URL:{SITE}/resort/{rid}/",
                  f"LOCATION:{esc(m['name'])}", f"GEO:{m['lat']:.4f};{m['lon']:.4f}", "TRANSP:TRANSPARENT",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def write_feeds(out_dir: Path, planner: dict, now: datetime, groups: Optional[list[dict]] = None) -> int:
    """Write every feed; returns the number of files."""
    groups = load_groups() if groups is None else groups
    region_names = {r["id"]: r for r in planner.get("regions") or []}
    group_names = {f"g-{g['id']}": g for g in groups}
    days = powder_days(planner, now)
    n = 0
    for slug, regions in areas(region_names, groups).items():
        for pas in PASSES:
            evs = [e for e in days if e[1]["region"] in regions and (pas == "all" or e[1]["passes"].get(pas))]
            for lang in LANGS:
                named = group_names.get(slug) or region_names.get(slug)
                area = ("全部地区" if lang == "zh" else "All areas") if slug == "all" else \
                    (named.get("name_zh") or named["name"]) if lang == "zh" else named["name"]
                pass_name = {"all": "全部雪场" if lang == "zh" else "All resorts", "ikon": "Ikon", "epic": "Epic"}[pas]
                title = f"{'粉雪日' if lang == 'zh' else 'Powder days'} · {pass_name} · {area}"
                p = out_dir / "ics" / lang / pas / f"{slug}.ics"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(calendar(lang, title, evs, now), encoding="utf-8", newline="")
                n += 1
    return n
