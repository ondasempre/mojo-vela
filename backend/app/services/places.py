"""Everything ashore: parking, food, picnic, clubs, services, webcams, events.

Design decision worth stating, because it shapes the whole feature. POIs are fetched
**only for the spot you open**, never for all 30 candidates in a ranking. Overpass is
donated infrastructure with a rate limit measured in a couple of requests per second,
and one query per candidate would be both slow and rude. Ranking therefore uses POI
data only when it happens to be cached already; the detail view fetches on demand and
caches for a day.

Consequence you can see in the UI: the accessibility component starts as UNKNOWN and
becomes a real number once you have opened that spot at least once. That is the honest
behaviour, and it is better than blocking a ranking for a minute to fill it in.
"""

from __future__ import annotations

from dataclasses import dataclass

from sailwise_ref.score import AccessibilityInput

from ..adapters.cache_memory import MemoryCache, cache_key, geohash_key
from ..adapters.events import CuratedEventsProvider, EventsResult, IcsEventsProvider, merge_events
from ..adapters.poi_overpass import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS_IT,
    OverpassPoiProvider,
    Place,
    PlacesResult,
)
from ..adapters.webcams import CuratedWebcamProvider, WebcamResult, WindyWebcamProvider

#: Sections shown in the UI, in order. Each maps to POI categories.
SECTIONS: list[tuple[str, str, str, list[str]]] = [
    ("launch", "⛵", "Messa in acqua", ["slipway", "marina"]),
    ("parking_car", "🅿️", "Parcheggio auto", ["parking"]),
    ("parking_moto", "🏍️", "Parcheggio moto", ["motorcycle_parking"]),
    ("food", "🍝", "Dove mangiare", ["restaurant", "bar", "cafe", "ice_cream"]),
    ("picnic", "🧺", "Aree picnic e spiagge", ["picnic", "beach"]),
    ("clubs", "🏛️", "Circoli velici", ["sailing_club"]),
    ("services", "🔧", "Servizi", ["fuel", "drinking_water", "toilets", "shower", "boat_service"]),
]

#: A parking within this distance of the launch is as good as it gets.
PARKING_IDEAL_M = 150
#: Beyond this, carrying a rig starts to hurt.
PARKING_FAR_M = 800

POI_TTL_S = 24 * 3600
WEBCAM_TTL_S = 6 * 3600
EVENTS_TTL_S = 6 * 3600


@dataclass(frozen=True)
class ParkingAssessment:
    """A score for the nearest usable parking, with the reasons spelled out."""

    score: float | None
    nearest_m: int | None
    free: bool | None
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "score": None if self.score is None else round(self.score, 2),
            "nearest_m": self.nearest_m,
            "free": self.free,
            "reasons": self.reasons,
        }


class PlacesService:
    def __init__(
        self,
        poi: OverpassPoiProvider,
        cache: MemoryCache,
        curated_webcams: CuratedWebcamProvider,
        curated_events: CuratedEventsProvider,
        windy_webcams: WindyWebcamProvider | None = None,
        ics: IcsEventsProvider | None = None,
        radius_m: int = 2000,
    ) -> None:
        self._poi = poi
        self._cache = cache
        self._webcams = curated_webcams
        self._events = curated_events
        self._windy = windy_webcams
        self._ics = ics
        self._radius_m = radius_m

    # --- points of interest ----------------------------------------------

    def _poi_key(self, lat: float, lon: float) -> str:
        return cache_key("poi", self._poi.id, geohash_key(lat, lon, 3), str(self._radius_m))

    def cached_places(self, lat: float, lon: float) -> PlacesResult | None:
        hit = self._cache.get(self._poi_key(lat, lon))
        return hit[0] if hit else None

    async def places_for(self, lat: float, lon: float, force: bool = False) -> PlacesResult:
        key = self._poi_key(lat, lon)
        if not force:
            hit = self._cache.get(key)
            if hit:
                return hit[0]

        result = await self._poi.around(lat, lon, self._radius_m)
        if result.error:
            # Serve stale rather than nothing — a day-old list of restaurants is fine.
            stale = self._cache.get_stale(key)
            if stale:
                return stale[0]
        else:
            self._cache.set(key, result, POI_TTL_S)
        return result

    def sections_from(self, result: PlacesResult, limit_per_section: int = 8) -> list[dict]:
        grouped = result.by_category()
        sections = []
        for key, emoji, label, categories in SECTIONS:
            places: list[Place] = []
            for category in categories:
                places.extend(grouped.get(category, []))
            places.sort(key=lambda p: p.distance_m)
            sections.append(
                {
                    "id": key,
                    "emoji": emoji,
                    "label": label,
                    "count": len(places),
                    "places": [p.as_dict() for p in places[:limit_per_section]],
                }
            )
        return sections

    # --- parking ----------------------------------------------------------

    def assess_parking(self, result: PlacesResult, motorcycle: bool = False) -> ParkingAssessment:
        category = "motorcycle_parking" if motorcycle else "parking"
        candidates = result.by_category().get(category, [])
        if not candidates:
            return ParkingAssessment(
                score=None,
                nearest_m=None,
                free=None,
                reasons=["nessun parcheggio mappato entro il raggio di ricerca"],
            )

        nearest = candidates[0]
        reasons: list[str] = []

        # Distance: 1.0 at or under the ideal, 0.0 at or beyond the far limit.
        span = PARKING_FAR_M - PARKING_IDEAL_M
        distance_score = max(0.0, min(1.0, (PARKING_FAR_M - nearest.distance_m) / span))
        reasons.append(f"il più vicino è a {nearest.distance_m} m dal punto di partenza")

        fee = nearest.tags.get("fee")
        free: bool | None = None
        fee_score = 0.6  # unknown: neither rewarded nor punished
        if fee in {"no", "false"}:
            free, fee_score = True, 1.0
            reasons.append("gratuito secondo OpenStreetMap")
        elif fee in {"yes", "true"}:
            free, fee_score = False, 0.5
            charge = nearest.tags.get("charge")
            reasons.append(
                f"a pagamento ({charge})" if charge else "a pagamento, tariffa sconosciuta"
            )
        else:
            reasons.append("non sappiamo se sia a pagamento")

        capacity_score = 0.6
        capacity = nearest.tags.get("capacity")
        if capacity and capacity.isdigit():
            value = int(capacity)
            capacity_score = min(1.0, value / 50.0)
            reasons.append(f"capienza dichiarata {value} posti")

        alternatives = len(candidates)
        if alternatives > 1:
            reasons.append(f"{alternatives} parcheggi entro il raggio")

        score = 0.55 * distance_score + 0.25 * fee_score + 0.20 * capacity_score
        return ParkingAssessment(
            score=score, nearest_m=nearest.distance_m, free=free, reasons=reasons
        )

    def accessibility_from(self, result: PlacesResult) -> AccessibilityInput:
        """Turn real POI data into the accessibility sub-factors.

        Only what OSM actually says. No slipway mapped nearby means the launch factor
        stays UNKNOWN rather than 0 — plenty of real ramps are simply not mapped yet,
        and scoring an absence of data as an absence of ramp would punish exactly the
        quiet spots this app is meant to find (FR-P-03).
        """
        grouped = result.by_category()

        launch: float | None = None
        if grouped.get("slipway"):
            launch = 1.0
        elif grouped.get("marina"):
            launch = 0.8
        elif grouped.get("beach"):
            launch = 0.6

        parking = self.assess_parking(result)
        service_count = sum(
            len(grouped.get(category, []))
            for category in ("fuel", "drinking_water", "toilets", "shower", "boat_service")
        )
        food_count = sum(
            len(grouped.get(category, []))
            for category in ("restaurant", "bar", "cafe", "ice_cream")
        )
        services = min(1.0, (service_count + food_count) / 6.0) if result.places else None

        return AccessibilityInput(launch=launch, parking=parking.score, services=services)

    # --- webcams ----------------------------------------------------------

    async def webcams_for(self, lat: float, lon: float, water_body: str | None) -> WebcamResult:
        key = cache_key("webcams", "mixed", geohash_key(lat, lon, 2))
        hit = self._cache.get(key)
        if hit:
            return hit[0]

        sources: list[str] = []
        found = await self._webcams.near(lat, lon)
        if found:
            sources.append("curated")
        if water_body:
            by_lake = self._webcams.by_water_body(water_body)
            known = {w.id for w in found}
            found.extend(w for w in by_lake if w.id not in known)

        error = None
        if self._windy is not None:
            try:
                windy = await self._windy.near(lat, lon)
                if windy:
                    found.extend(windy)
                    sources.append("windy")
            except Exception as exc:
                error = f"Windy Webcams non raggiungibile: {type(exc).__name__}"

        result = WebcamResult(webcams=found, sources=sources, error=error)
        self._cache.set(key, result, WEBCAM_TTL_S)
        return result

    # --- events -----------------------------------------------------------

    async def events_for(self, water_body: str | None) -> EventsResult:
        key = cache_key("events", "mixed", water_body or "all")
        hit = self._cache.get(key)
        if hit:
            return hit[0]

        groups = [self._events.upcoming(water_body)]
        sources = ["curated"] if groups[0] else []

        if self._ics is not None:
            for feed in self._events.feeds:
                if water_body and feed.get("water_body") not in (None, water_body):
                    continue
                if not feed.get("url"):
                    continue
                fetched = await self._ics.fetch(feed["url"], feed.get("water_body"))
                if fetched:
                    groups.append(fetched)
                    sources.append(feed.get("name") or feed["url"])

        merged = merge_events(groups)
        note = (
            None
            if merged
            else (
                "Nessun evento verificato per questo lago. SailWise non inventa "
                "calendari di regate: aggiungi eventi in data/events/events.json "
                "oppure il feed ICS del tuo circolo."
            )
        )
        result = EventsResult(events=merged, sources=sources, note=note)
        self._cache.set(key, result, EVENTS_TTL_S)
        return result


def category_metadata() -> dict:
    """Emoji and Italian labels, so the UI does not hardcode a second copy."""
    return {
        key: {"emoji": CATEGORY_EMOJI.get(key, "📍"), "label": CATEGORY_LABELS_IT.get(key, key)}
        for key in CATEGORY_LABELS_IT
    }
