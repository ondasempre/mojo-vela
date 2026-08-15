"""Live webcams near a sailing spot.

A webcam is the one thing that beats every forecast: it shows you the water *now*.
There is, however, no free open webcam API for Italian lakes, so this module offers
two honest routes and no third one:

1. **A curated dataset** (`data/webcams/<dataset>.json`) — links a human checked,
   each with an owner and a URL. This is the route that costs nothing and works
   today. Add cameras you already use.
2. **The Windy Webcams API** — real coverage, but it needs an API key and its own
   terms. Off unless `WINDY_WEBCAMS_API_KEY` is set.

What this module will never do is guess a webcam URL. A plausible-looking link to a
camera that does not exist is worse than an empty section, because the sailor plans
around having a look and then has nothing.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import httpx

WINDY_ENDPOINT = "https://api.windy.com/webcams/api/v3/webcams"
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Webcam:
    id: str
    title: str
    lat: float | None
    lon: float | None
    #: Page to open. Always present — a webcam entry without a link is not an entry.
    url: str
    #: Still image, when the source publishes one that may be embedded.
    image_url: str | None = None
    #: Embeddable player URL, when the source allows embedding.
    embed_url: str | None = None
    provider: str = "curated"
    owner: str | None = None
    distance_km: float | None = None
    last_updated: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "image_url": self.image_url,
            "embed_url": self.embed_url,
            "provider": self.provider,
            "owner": self.owner,
            "lat": self.lat,
            "lon": self.lon,
            "distance_km": None if self.distance_km is None else round(self.distance_km, 1),
            "last_updated": self.last_updated,
            "note": self.note,
        }


@dataclass(frozen=True)
class WebcamResult:
    webcams: list[Webcam]
    sources: list[str]
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "webcams": [w.as_dict() for w in self.webcams],
            "sources": self.sources,
            "error": self.error,
        }


class CuratedWebcamProvider:
    """Webcams from a local, human-checked file. Always available, never guesses."""

    id = "curated"

    def __init__(self, data_dir: Path, dataset: str = "webcams") -> None:
        self._path = data_dir / "webcams" / f"{dataset}.json"
        self._entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = payload.get("webcams", [])
        except (json.JSONDecodeError, OSError):
            self._entries = []

    async def near(self, lat: float, lon: float, radius_km: float = 15.0) -> list[Webcam]:
        found: list[Webcam] = []
        for entry in self._entries:
            if not entry.get("url"):
                continue  # an entry without a link is not usable

            cam_lat = entry.get("lat")
            cam_lon = entry.get("lon")
            distance = None
            if cam_lat is not None and cam_lon is not None:
                distance = haversine_km(lat, lon, float(cam_lat), float(cam_lon))
                if distance > radius_km:
                    continue
            elif entry.get("water_body") is None:
                continue  # no position and no lake: cannot place it

            found.append(
                Webcam(
                    id=str(entry.get("id") or entry["url"]),
                    title=entry.get("title") or "Webcam",
                    lat=cam_lat,
                    lon=cam_lon,
                    url=entry["url"],
                    image_url=entry.get("image_url"),
                    embed_url=entry.get("embed_url"),
                    provider="curated",
                    owner=entry.get("owner"),
                    distance_km=distance,
                    last_updated=entry.get("verified_at"),
                    note=entry.get("note"),
                )
            )
        found.sort(key=lambda w: (w.distance_km is None, w.distance_km or 0))
        return found

    def by_water_body(self, water_body: str) -> list[Webcam]:
        return [
            Webcam(
                id=str(e.get("id") or e["url"]),
                title=e.get("title") or "Webcam",
                lat=e.get("lat"),
                lon=e.get("lon"),
                url=e["url"],
                image_url=e.get("image_url"),
                embed_url=e.get("embed_url"),
                owner=e.get("owner"),
                last_updated=e.get("verified_at"),
                note=e.get("note"),
            )
            for e in self._entries
            if e.get("water_body") == water_body and e.get("url")
        ]


class WindyWebcamProvider:
    """Windy Webcams API. Requires a key and acceptance of Windy's terms.

    Disabled unless a key is configured — see ADR 0002 for why every Windy
    integration in this project is opt-in rather than default.
    """

    id = "windy-webcams"

    def __init__(self, client: httpx.AsyncClient, api_key: str, timeout_s: int = 20) -> None:
        self._client = client
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def near(self, lat: float, lon: float, radius_km: float = 15.0) -> list[Webcam]:
        params = {
            "nearby": f"{lat:.4f},{lon:.4f},{int(radius_km)}",
            "include": "images,location,urls",
            "limit": "10",
        }
        response = await self._client.get(
            WINDY_ENDPOINT,
            params=params,
            headers={"x-windy-api-key": self._api_key},
            timeout=self._timeout_s,
        )
        response.raise_for_status()
        return self.parse(response.json(), lat, lon)

    def parse(self, payload: dict, lat: float, lon: float) -> list[Webcam]:
        webcams: list[Webcam] = []
        for item in payload.get("webcams", []):
            location = item.get("location") or {}
            urls = item.get("urls") or {}
            images = item.get("images") or {}
            current = images.get("current") or {}

            detail = urls.get("detail")
            page = detail.get("desktop") if isinstance(detail, dict) else detail
            if not page:
                continue  # no link, no entry

            cam_lat = location.get("latitude")
            cam_lon = location.get("longitude")
            webcams.append(
                Webcam(
                    id=str(item.get("webcamId") or item.get("id")),
                    title=item.get("title") or "Webcam",
                    lat=cam_lat,
                    lon=cam_lon,
                    url=page,
                    image_url=current.get("preview") or current.get("thumbnail"),
                    provider="windy",
                    owner=location.get("city"),
                    distance_km=(
                        haversine_km(lat, lon, float(cam_lat), float(cam_lon))
                        if cam_lat is not None and cam_lon is not None
                        else None
                    ),
                    last_updated=item.get("lastUpdatedOn"),
                    note="Windy Webcams — image tokens expire; open the link for the live view.",
                )
            )
        webcams.sort(key=lambda w: (w.distance_km is None, w.distance_km or 0))
        return webcams


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
