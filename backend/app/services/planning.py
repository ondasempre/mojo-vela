"""The planning service: fetch, cache, compute, rank, attribute.

This is the orchestration layer from docs/03-system-architecture.md, step [3] to [8]
of the UC-1 data flow. It owns the I/O and the assembly; it owns no numerics — every
number comes from `sailwise_ref`, which is the same engine the Mojo core mirrors.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from sailwise_ref.profiles import SailingProfile
from sailwise_ref.ranking import RankingResult, SpotInput, rank_spots
from sailwise_ref.safety import DISCLAIMER
from sailwise_ref.score import AccessibilityInput

from ..adapters.cache_memory import MemoryCache, cache_key, geohash_key
from ..ports import Forecast, WeatherProvider
from .spots import Spot, SpotService


class PlanningService:
    def __init__(
        self,
        spots: SpotService,
        provider: WeatherProvider,
        fallback: WeatherProvider,
        cache: MemoryCache,
        forecast_ttl_s: int,
        max_spots: int,
    ) -> None:
        self._spots = spots
        self._provider = provider
        self._fallback = fallback
        self._cache = cache
        self._ttl = forecast_ttl_s
        self._max_spots = max_spots
        self._places = None

    def attach_places(self, places) -> None:
        """Optional PlacesService, used for accessibility when POI data is cached.

        Ranking never *fetches* POIs — that would mean one Overpass query per
        candidate. It only uses what opening a spot has already cached, so
        accessibility fills in as you explore rather than blocking a ranking.
        """
        self._places = places

    # --- forecasts --------------------------------------------------------

    async def forecast_for(self, spot: Spot, day: date) -> tuple[Forecast | None, str | None]:
        """Return (forecast, error). Cache first, provider second, stale third.

        The order matters and is the reliability contract (NFR-R-01, FR-C-05):
        a provider outage degrades to clearly-labelled stale data, never to an
        error, and never to a fabricated value.
        """
        if spot.lat is None or spot.lon is None:
            return None, "no coordinates: the spot has not been geocoded yet"

        key = cache_key(
            "forecast",
            self._provider.id,
            geohash_key(spot.lat, spot.lon),
            day.isoformat(),
            spot.timezone,
        )

        hit = self._cache.get(key)
        if hit is not None:
            forecast, info = hit
            return _with_cache(forecast, info), None

        try:
            forecast = await self._provider.hourly(
                spot.id, spot.lat, spot.lon, day, spot.timezone
            )
            self._cache.set(key, forecast, self._ttl)
            return forecast, None
        except Exception as exc:  # provider failures are expected, not exceptional
            stale = self._cache.get_stale(key)
            if stale is not None:
                forecast, info = stale
                return _with_cache(forecast, info), None

            if self._provider is not self._fallback:
                try:
                    forecast = await self._fallback.hourly(
                        spot.id, spot.lat, spot.lon, day, spot.timezone
                    )
                    return forecast, None
                except Exception:
                    pass
            return None, f"{type(exc).__name__}: {exc}"

    # --- the primary use case --------------------------------------------

    async def recommend(
        self,
        profile: SailingProfile,
        day: date,
        *,
        origin_spot_id: str | None = None,
        origin: tuple[float, float] | None = None,
        max_driving_km: float | None = None,
        earliest_hour: int = 8,
        latest_hour: int = 20,
        min_duration_h: int = 3,
        needs_ramp: bool = False,
        gust_limit_kn: float | None = None,
        water_body: str | None = None,
        limit: int = 8,
    ) -> dict:
        candidates = [
            s
            for s in self._spots.all()
            if water_body is None or s.water_body == water_body
        ]

        origin_spot = self._spots.get(origin_spot_id) if origin_spot_id else None
        if origin_spot is not None:
            await self._spots.resolve(origin_spot)
            if origin is None and origin_spot.lat is not None:
                origin = (origin_spot.lat, origin_spot.lon)

        # Only already-resolved spots are scored. Geocoding happens in the startup
        # warm-up, not on the request path: at one request per second, resolving
        # inline would hold the user for a minute on first run.
        candidates = candidates[: self._max_spots]
        resolved = [s for s in candidates if s.lat is not None]
        unresolved = [s for s in candidates if s.lat is None]

        forecasts = await asyncio.gather(
            *(self.forecast_for(spot, day) for spot in resolved)
        )

        inputs: list[SpotInput] = []
        problems: list[dict] = []
        sources: dict[str, dict] = {}
        demo_mode = False

        for spot, (forecast, error) in zip(resolved, forecasts, strict=True):
            if forecast is None:
                problems.append({"id": spot.id, "name": spot.name, "reason": error})
                continue

            if forecast.provenance == "SYNTHETIC":
                demo_mode = True
            sources.setdefault(
                forecast.provider_id,
                {
                    "id": forecast.provider_id,
                    "kind": "weather",
                    "model": forecast.model_id,
                    "provenance": forecast.provenance,
                    "attribution": forecast.attribution,
                    "retrieved_at": forecast.retrieved_at,
                    "cache": forecast.cache.as_dict(),
                    "notes": forecast.notes,
                },
            )

            hours = [h for h in forecast.hours if earliest_hour <= h.hour <= latest_hour]
            if not hours:
                problems.append(
                    {"id": spot.id, "name": spot.name, "reason": "no forecast in that time range"}
                )
                continue

            inputs.append(
                SpotInput(
                    id=spot.id,
                    name=spot.name,
                    lat=spot.lat,
                    lon=spot.lon,
                    hours=hours,
                    water_body=spot.water_body_name or spot.water_body,
                    water_body_id=spot.water_body,
                    accessibility=self._accessibility_for(spot),
                    has_ramp=self._has_ramp(spot),
                    verified=spot.verified,
                )
            )

        ranking: RankingResult = rank_spots(
            inputs,
            profile,
            origin=origin,
            max_driving_km=max_driving_km,
            min_duration_h=min_duration_h,
            needs_ramp=needs_ramp,
            gust_limit_kn=gust_limit_kn,
            limit=limit,
        )

        payload = ranking.as_dict()
        payload["excluded"].extend(
            {"id": p["id"], "name": p["name"], "reason": p["reason"]} for p in problems
        )
        if unresolved:
            payload["excluded"].extend(
                {
                    "id": s.id,
                    "name": s.name,
                    "reason": (
                        "coordinates not resolved yet"
                        if self._spots.status()["warming"]
                        else "coordinates not resolved (geocoding disabled or unavailable)"
                    ),
                }
                for s in unresolved
            )

        meta = _meta(sources, demo_mode, self._cache.stats())
        meta["spots"] = self._spots.status()
        return {"data": payload, "meta": meta}

    async def plan_for_spot(
        self,
        spot: Spot,
        profile: SailingProfile,
        day: date,
        *,
        earliest_hour: int = 8,
        latest_hour: int = 20,
        min_duration_h: int = 3,
        gust_limit_kn: float | None = None,
    ) -> dict:
        await self._spots.resolve(spot)
        forecast, error = await self.forecast_for(spot, day)
        if forecast is None:
            return {"data": None, "error": error, "meta": _meta({}, False, self._cache.stats())}

        hours = [h for h in forecast.hours if earliest_hour <= h.hour <= latest_hour]
        ranking = rank_spots(
            [
                SpotInput(
                    id=spot.id,
                    name=spot.name,
                    lat=spot.lat,
                    lon=spot.lon,
                    hours=hours,
                    water_body=spot.water_body_name or spot.water_body,
                    water_body_id=spot.water_body,
                    accessibility=self._accessibility_for(spot),
                    has_ramp=self._has_ramp(spot),
                    verified=spot.verified,
                )
            ],
            profile,
            min_duration_h=min_duration_h,
            gust_limit_kn=gust_limit_kn,
        )

        sources = {
            forecast.provider_id: {
                "id": forecast.provider_id,
                "kind": "weather",
                "model": forecast.model_id,
                "provenance": forecast.provenance,
                "attribution": forecast.attribution,
                "retrieved_at": forecast.retrieved_at,
                "cache": forecast.cache.as_dict(),
                "notes": forecast.notes,
            }
        }
        result = ranking.results[0].as_dict() if ranking.results else None
        return {
            "data": result,
            "meta": _meta(sources, forecast.provenance == "SYNTHETIC", self._cache.stats()),
        }


    def _cached_places(self, spot: Spot):
        if self._places is None or spot.lat is None or spot.lon is None:
            return None
        return self._places.cached_places(spot.lat, spot.lon)

    def _accessibility_for(self, spot: Spot) -> AccessibilityInput:
        """Real POI data when we have it cached, the ingested dataset otherwise."""
        cached = self._cached_places(spot)
        if cached is not None and cached.places:
            return self._places.accessibility_from(cached)
        return _accessibility_from_dataset(spot)

    def _has_ramp(self, spot: Spot) -> bool | None:
        """True only on evidence. No evidence stays None, which never satisfies a filter."""
        cached = self._cached_places(spot)
        if cached is not None and cached.places:
            grouped = cached.by_category()
            if grouped.get("slipway") or grouped.get("marina"):
                return True
        return spot.has_ramp


def _accessibility_from_dataset(spot: Spot) -> AccessibilityInput:
    """Only what is actually known. Everything else stays UNKNOWN (FR-P-03).

    Until POIs have been fetched for this spot, this is empty for most of them —
    which is why the accessibility component shows UNKNOWN in the UI instead of a
    made-up 7/10.
    """
    facilities = spot.facilities or {}
    launch = facilities.get("launch_point")
    parking = facilities.get("parking")

    launch_score: float | None = None
    if launch is not None:
        launch_score = 1.0 if launch else 0.0

    parking_score: float | None = None
    if parking is not None:
        parking_score = min(1.0, len(parking) / 2.0) if isinstance(parking, list) else None

    services: float | None = None
    countable = [
        facilities.get(key)
        for key in ("restaurants", "fuel", "sailing_clubs", "marina", "boat_services")
    ]
    known = [c for c in countable if c is not None]
    if known:
        services = min(1.0, sum(len(c) if isinstance(c, list) else 0 for c in known) / 4.0)

    return AccessibilityInput(launch=launch_score, parking=parking_score, services=services)


def _with_cache(forecast: Forecast, info) -> Forecast:
    return Forecast(
        spot_id=forecast.spot_id,
        day=forecast.day,
        hours=forecast.hours,
        provider_id=forecast.provider_id,
        model_id=forecast.model_id,
        provenance=forecast.provenance,
        attribution=forecast.attribution,
        issued_at=forecast.issued_at,
        retrieved_at=forecast.retrieved_at,
        cache=info,
        notes=forecast.notes,
    )


def _meta(sources: dict, demo_mode: bool, cache_stats: dict) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": list(sources.values()),
        "cache": cache_stats,
        "demo_mode": demo_mode,
        "disclaimer": DISCLAIMER,
    }
