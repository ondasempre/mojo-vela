"""Ports: the interfaces the services depend on.

Services import from here. They never import from `adapters/`. That single rule is
what makes "swap the weather provider" a configuration change rather than a refactor
(ADR 0002), and it is what lets every test run against the fixture provider without
touching a live service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from sailwise_ref.weather import HourlyWeather


@dataclass(frozen=True)
class CacheInfo:
    """How a value was served. Surfaced in the API and shown in the UI (FR-C-04)."""

    state: str  # MISS | HIT | STALE
    age_s: int | None = None
    ttl_s: int | None = None

    def as_dict(self) -> dict:
        return {"state": self.state, "age_s": self.age_s, "ttl_s": self.ttl_s}


@dataclass(frozen=True)
class ProviderCapabilities:
    """What an adapter can actually supply. Absent fields become UNKNOWN, never zero."""

    waves: bool = False
    visibility: bool = True
    storm_probability: bool = False


@dataclass(frozen=True)
class Forecast:
    """A normalised day of weather, with everything needed to attribute it."""

    spot_id: str
    day: date
    hours: list[HourlyWeather]
    provider_id: str
    model_id: str | None = None
    provenance: str = "FORECAST"
    attribution: str | None = None
    issued_at: str | None = None
    retrieved_at: str | None = None
    cache: CacheInfo = field(default_factory=lambda: CacheInfo(state="MISS"))
    notes: list[str] = field(default_factory=list)


class WeatherProvider(Protocol):
    id: str

    def capabilities(self) -> ProviderCapabilities: ...

    async def hourly(
        self, spot_id: str, lat: float, lon: float, day: date, timezone: str
    ) -> Forecast: ...


class Geocoder(Protocol):
    async def geocode(self, query: str) -> tuple[float, float, str] | None:
        """Return (lat, lon, display_name), or None when nothing was found.

        Never returns a guess. A failed lookup leaves the spot without coordinates,
        and the spot is reported as unresolved rather than placed approximately.
        """
        ...


class Cache(Protocol):
    def get(self, key: str) -> tuple[object, CacheInfo] | None: ...

    def set(self, key: str, value: object, ttl_s: int) -> None: ...

    def get_stale(self, key: str) -> tuple[object, CacheInfo] | None: ...

    def invalidate(self, prefix: str | None = None) -> int: ...

    def stats(self) -> dict: ...
