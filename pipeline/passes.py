"""Lower-tier pass products (data/pass_products.yaml, design doc B2): Ikon Base, Epic Local.

    access(products) -> {product id: {resort id: Access}}
    blocked(acc, "2026-12-27") -> True on a blackout date

The top tier (Ikon Pass, Epic Pass) stays in data/resorts.yaml `passes`.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import yaml

PRODUCTS_FILE = Path(__file__).resolve().parents[1] / "data" / "pass_products.yaml"


class Access(TypedDict):
    days: str | int             # "unlimited" or a number of days
    shared: bool                # the days are a total across the entry's resorts
    blackout: list[list[str]]   # [first, last] ISO dates, inclusive
    consecutive: bool           # the days must be taken in a row


def load_products(path: Path | str = PRODUCTS_FILE) -> list[dict]:
    return (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("products") or []


def _iso(d) -> str:
    return d if isinstance(d, str) else d.isoformat()


def merge(ranges: list[list[str]]) -> list[list[str]]:
    """Sorted, overlapping or touching ranges joined (ISO dates compare as strings)."""
    out: list[list[str]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def access(products: list[dict]) -> dict[str, dict[str, Access]]:
    out: dict[str, dict[str, Access]] = {}
    for p in products:
        base = [[_iso(a), _iso(b)] for a, b in p.get("blackout") or []]
        acc: dict[str, Access] = {}
        for e in p["access"]:
            ranges = merge((base if e.get("blackout") else []) + [[_iso(a), _iso(b)] for a, b in e.get("extra") or []])
            for rid in e["resorts"]:
                if rid in acc:
                    raise ValueError(f"{p['id']}: {rid} listed twice")
                acc[rid] = {"days": e["days"], "shared": bool(e.get("shared")), "blackout": ranges, "consecutive": bool(e.get("consecutive"))}
        out[p["id"]] = acc
    return out


def blocked(acc: Access, day: str) -> bool:
    return any(a <= day <= b for a, b in acc["blackout"])
