"""Read-only access to the previously published data set.

The GitHub Pages deployment is replaced as a whole on every run, and most
resorts are only refreshed once a day, so each run starts from the last
published files: documents that are not due are copied over unchanged, and the
cached ensemble member totals (`ens/{id}.json`) are reused between refreshes.
The source is a URL (the live site) or a local directory.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx

from .config import SCHEMA_VERSION

log = logging.getLogger(__name__)
DEFAULT_PREVIOUS = "https://tokenflyai.github.io/snow/data/v1"


def parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def age_hours(s: Optional[str], now: datetime) -> Optional[float]:
    t = parse_time(s)
    return None if t is None else (now - t).total_seconds() / 3600.0


class Previous:
    def __init__(self, base: Optional[str], client: Optional[httpx.Client] = None):
        self.base = None if not base or base == "none" else base.rstrip("/")
        self.is_url = bool(self.base and self.base.startswith(("http://", "https://")))
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0, follow_redirects=True,
                                        headers={"User-Agent": "snow-forecast-pipeline/0.2"})
        return self._client

    def get(self, rel: str) -> Optional[dict]:
        """One published JSON document, or None when it is missing, unreadable or from another schema."""
        if not self.base:
            return None
        try:
            if self.is_url:
                for attempt in range(3):
                    r = self._http().get(f"{self.base}/{rel}")
                    if r.status_code == 404:
                        return None
                    if r.status_code == 200:
                        doc = r.json()
                        break
                else:
                    return None
            else:
                p = Path(self.base) / rel
                if not p.exists():
                    return None
                doc = json.loads(p.read_text(encoding="utf-8"))
        except (httpx.HTTPError, ValueError, OSError) as e:
            log.warning("previous %s unreadable: %s", rel, e)
            return None
        if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
            return None
        return doc

    def get_many(self, rels: Iterable[str], workers: int = 8) -> dict[str, Optional[dict]]:
        rels = list(rels)
        if not rels or not self.base:
            return {r: None for r in rels}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return dict(zip(rels, ex.map(self.get, rels)))
