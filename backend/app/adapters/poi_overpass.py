"""Points of interest around a sailing spot, from OpenStreetMap via Overpass.

What this brings in: car parking, **motorcycle parking**, restaurants, osterie, bars,
cafés, ice cream, picnic sites and tables, sailing clubs, marinas, slipways, fuel,
drinking water, toilets and showers, boat shops.

Usage policy (docs/06-integrations.md, checked 2026-08-15): public Overpass instances
support a few hundred moderate queries per day and are run on donated hardware. This
adapter therefore serialises requests behind a minimum interval, sends an identifying
User-Agent, caches results for a day, and fetches **one query per spot** rather than
one per category. For bulk ingestion use a Geofabrik extract instead.

Licence: ODbL. "© OpenStreetMap contributors" must be displayed wherever this data
appears — the attribution travels in the payload for that reason.

Nothing here is invented. A missing tag stays `None` and renders as "sconosciuto".
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

ENDPOINT = "https://overpass-api.de/api/interpreter"
ATTRIBUTION = "© OpenStreetMap contributors"

#: Public instances are shared and donated. Stay well under a request per second.
MIN_INTERVAL_S = 2.0

EARTH_RADIUS_M = 6_371_000.0

# One query per spot, covering every category we care about. `nwr` matches nodes,
# ways and relations; `out center tags` gives a single representative coordinate for
# ways and relations, which is what we need for a distance.
QUERY_TEMPLATE = """
[out:json][timeout:50];
(
  nwr(around:{radius},{lat},{lon})["amenity"="parking"];
  nwr(around:{radius},{lat},{lon})["amenity"="motorcycle_parking"];
  nwr(around:{radius},{lat},{lon})["amenity"~"^(restaurant|bar|pub|cafe|fast_food|ice_cream|biergarten)$"];
  nwr(around:{radius},{lat},{lon})["tourism"="picnic_site"];
  nwr(around:{radius},{lat},{lon})["leisure"="picnic_table"];
  nwr(around:{radius},{lat},{lon})["club"="sailing"];
  nwr(around:{radius},{lat},{lon})["sport"="sailing"];
  nwr(around:{radius},{lat},{lon})["leisure"="marina"];
  nwr(around:{radius},{lat},{lon})["leisure"="slipway"];
  nwr(around:{radius},{lat},{lon})["amenity"="fuel"];
  nwr(around:{radius},{lat},{lon})["amenity"="drinking_water"];
  nwr(around:{radius},{lat},{lon})["amenity"="toilets"];
  nwr(around:{radius},{lat},{lon})["amenity"="shower"];
  nwr(around:{radius},{lat},{lon})["shop"="boat"];
  nwr(around:{radius},{lat},{lon})["natural"="beach"];
);
out center tags;
"""

#: Category → emoji, used by the UI. Kept next to the classifier so a new category
#: cannot be added without deciding how it looks.
CATEGORY_EMOJI = {
    "parking": "🅿️",
    "motorcycle_parking": "🏍️",
    "restaurant": "🍝",
    "bar": "🍺",
    "cafe": "☕",
    "ice_cream": "🍨",
    "picnic": "🧺",
    "sailing_club": "⛵",
    "marina": "⚓",
    "slipway": "🛥️",
    "fuel": "⛽",
    "drinking_water": "🚰",
    "toilets": "🚻",
    "shower": "🚿",
    "boat_service": "🔧",
    "beach": "🏖️",
}

CATEGORY_LABELS_IT = {
    "parking": "Parcheggio auto",
    "motorcycle_parking": "Parcheggio moto",
    "restaurant": "Ristorante / osteria",
    "bar": "Bar / pub",
    "cafe": "Caffè",
    "ice_cream": "Gelateria",
    "picnic": "Area picnic",
    "sailing_club": "Circolo velico",
    "marina": "Porto / darsena",
    "slipway": "Scivolo",
    "fuel": "Carburante",
    "drinking_water": "Acqua potabile",
    "toilets": "Servizi igienici",
    "shower": "Docce",
    "boat_service": "Servizi nautici",
    "beach": "Spiaggia",
}

#: Tags worth keeping. Everything else is dropped: we display what we can explain.
KEEP_TAGS = frozenset({
    "name", "operator", "opening_hours", "phone", "contact:phone", "website",
    "contact:website", "email", "fee", "access", "capacity", "capacity:disabled",
    "capacity:charging", "parking", "surface", "covered", "maxstay", "supervised",
    "lit", "cuisine", "diet:vegetarian", "outdoor_seating", "wheelchair",
    "description", "sport", "club", "seasonal", "payment:cash", "payment:cards",
    "charge", "toilets", "drinking_water", "shelter", "bbq", "internet_access",
})


@dataclass(frozen=True)
class Place:
    """One point of interest. Every optional field is genuinely optional."""

    osm_type: str
    osm_id: int
    category: str
    name: str | None
    lat: float
    lon: float
    distance_m: int
    tags: dict = field(default_factory=dict)

    @property
    def osm_url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"

    @property
    def maps_url(self) -> str:
        """Google Maps link built from the coordinate — not a claim about a business.

        This is a URL constructed from a position we already have, which is why it is
        safe: it cannot point somewhere we do not know about.
        """
        return f"https://www.google.com/maps/search/?api=1&query={self.lat:.6f},{self.lon:.6f}"

    @property
    def directions_url(self) -> str:
        return f"https://www.google.com/maps/dir/?api=1&destination={self.lat:.6f},{self.lon:.6f}"

    def website(self) -> str | None:
        return self.tags.get("website") or self.tags.get("contact:website")

    def phone(self) -> str | None:
        return self.tags.get("phone") or self.tags.get("contact:phone")

    def as_dict(self) -> dict:
        return {
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "category": self.category,
            "category_label": CATEGORY_LABELS_IT.get(self.category, self.category),
            "emoji": CATEGORY_EMOJI.get(self.category, "📍"),
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "distance_m": self.distance_m,
            "walk_min": max(1, round(self.distance_m / 80.0)),  # ~4.8 km/h
            "tags": self.tags,
            "osm_url": self.osm_url,
            "maps_url": self.maps_url,
            "directions_url": self.directions_url,
            "website": self.website(),
            "phone": self.phone(),
            "opening_hours": self.tags.get("opening_hours"),
            "fee": self.tags.get("fee"),
            "capacity": self.tags.get("capacity"),
            "cuisine": self.tags.get("cuisine"),
        }


@dataclass(frozen=True)
class PlacesResult:
    places: list[Place]
    attribution: str = ATTRIBUTION
    retrieved_at: str | None = None
    error: str | None = None

    def by_category(self) -> dict[str, list[Place]]:
        grouped: dict[str, list[Place]] = {}
        for place in self.places:
            grouped.setdefault(place.category, []).append(place)
        for items in grouped.values():
            items.sort(key=lambda p: p.distance_m)
        return grouped


class OverpassPoiProvider:
    id = "overpass"

    def __init__(self, client: httpx.AsyncClient, user_agent: str, timeout_s: int = 60) -> None:
        self._client = client
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def around(self, lat: float, lon: float, radius_m: int = 2000) -> PlacesResult:
        query = QUERY_TEMPLATE.format(radius=radius_m, lat=f"{lat:.6f}", lon=f"{lon:.6f}")

        async with self._lock:
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._client.post(
                    ENDPOINT,
                    data={"data": query},
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout_s,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                # A POI lookup failing must never break the plan. The section shows
                # "not available" and the rest of the page carries on.
                return PlacesResult(places=[], error=f"{type(exc).__name__}: {exc}")
            finally:
                self._last_request = time.monotonic()

        return self.parse(payload, lat, lon)

    def parse(self, payload: dict, lat: float, lon: float) -> PlacesResult:
        """Turn an Overpass response into places. Separated out so it is testable offline."""
        places: list[Place] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            category = classify(tags)
            if category is None:
                continue

            centre = element.get("center") or element
            place_lat = centre.get("lat")
            place_lon = centre.get("lon")
            if place_lat is None or place_lon is None:
                continue  # a way without a resolved centre: no position, no entry

            places.append(
                Place(
                    osm_type=element.get("type", "node"),
                    osm_id=int(element.get("id", 0)),
                    category=category,
                    name=tags.get("name"),
                    lat=float(place_lat),
                    lon=float(place_lon),
                    distance_m=round(haversine_m(lat, lon, float(place_lat), float(place_lon))),
                    tags={k: v for k, v in tags.items() if k in KEEP_TAGS},
                )
            )

        places.sort(key=lambda p: p.distance_m)
        return PlacesResult(
            places=places,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )


def classify(tags: dict) -> str | None:
    """Map OSM tags to one of our categories, or None to ignore the element."""
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")

    if amenity == "parking":
        return "parking"
    if amenity == "motorcycle_parking":
        return "motorcycle_parking"
    if amenity in {"restaurant", "fast_food", "biergarten"}:
        return "restaurant"
    if amenity in {"bar", "pub"}:
        return "bar"
    if amenity == "cafe":
        return "cafe"
    if amenity == "ice_cream":
        return "ice_cream"
    if tags.get("tourism") == "picnic_site" or leisure == "picnic_table":
        return "picnic"
    if tags.get("club") == "sailing" or (tags.get("sport") == "sailing" and leisure != "marina"):
        return "sailing_club"
    if leisure == "marina":
        return "marina"
    if leisure == "slipway":
        return "slipway"
    if amenity == "fuel":
        return "fuel"
    if amenity == "drinking_water":
        return "drinking_water"
    if amenity == "toilets":
        return "toilets"
    if amenity == "shower":
        return "shower"
    if tags.get("shop") == "boat":
        return "boat_service"
    if tags.get("natural") == "beach":
        return "beach"
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
