"""Resort database: schema + loader for data/resorts.yaml."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "resorts.yaml"

PassName = Literal["ikon", "epic"]
PassTier = Literal["unlimited", "7day", "5day", "2day"]
LEVELS = ("base", "mid", "summit")


class Elevation(BaseModel):
    base: int = Field(ge=0, le=5000)
    mid: int = Field(ge=0, le=5000)
    summit: int = Field(ge=0, le=5000)

    @model_validator(mode="after")
    def _ordered(self) -> "Elevation":
        if not (self.base < self.mid < self.summit):
            raise ValueError("elevations must satisfy base < mid < summit")
        return self

    def get(self, level: str) -> int:
        return getattr(self, level)


class Region(BaseModel):
    id: str
    name: str
    name_zh: str


class Resort(BaseModel):
    id: str
    name: str
    name_zh: Optional[str] = None
    destination: Optional[str] = None
    passes: dict[PassName, PassTier] = {}
    country: str = Field(min_length=2, max_length=2)
    state: Optional[str] = None
    region: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elevation_m: Elevation
    timezone: str
    snotel: Optional[str] = None
    needs_review: bool = False
    notes: Optional[str] = None
    sources: list[str] = []

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", v):
            raise ValueError(f"id must be a lowercase slug: {v!r}")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as e:  # ZoneInfoNotFoundError is not a ValueError
            raise ValueError(f"unknown timezone {v!r}") from e
        return v

    @field_validator("snotel")
    @classmethod
    def _snotel(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.fullmatch(r"\d+:[A-Z]{2}:SNTL", v):
            raise ValueError(f"snotel must look like '784:CA:SNTL': {v!r}")
        return v


class ResortDB(BaseModel):
    regions: list[Region]
    resorts: list[Resort]

    @model_validator(mode="after")
    def _consistent(self) -> "ResortDB":
        ids = [r.id for r in self.resorts]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate resort ids: {sorted(dup)}")
        region_ids = {r.id for r in self.regions}
        bad = sorted({r.region for r in self.resorts} - region_ids)
        if bad:
            raise ValueError(f"resorts reference unknown regions: {bad}")
        return self

    def by_id(self, rid: str) -> Resort:
        for r in self.resorts:
            if r.id == rid:
                return r
        raise KeyError(rid)


def load_resorts(path: Path | str = DEFAULT_PATH) -> ResortDB:
    with open(path, "r", encoding="utf-8") as f:
        return ResortDB.model_validate(yaml.safe_load(f))
