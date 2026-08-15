"""Spot catalogue: load the dataset, resolve coordinates, never invent one.

Three states a spot can be in, and the API reports which:

* **ingested** — coordinates came from `data/spots/<dataset>.json`, written by
  `scripts/fetch_spots.py` with a source and a retrieval date;
* **resolved** — coordinates came from a lazy Nominatim lookup at runtime, cached to
  disk; usable, and labelled unverified;
* **unresolved** — no coordinates. The spot is listed but cannot be scored, and it
  says so. It is never placed approximately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..ports import Geocoder


@dataclass
class Spot:
    id: str
    name: str
    query: str
    water_body: str | None = None
    water_body_name: str | None = None
    timezone: str = "Europe/Rome"
    lat: float | None = None
    lon: float | None = None
    priority: int = 3
    source: str | None = None
    retrieved_at: str | None = None
    display_name: str | None = None
    verified: bool = False
    has_ramp: bool | None = None
    facilities: dict = field(default_factory=dict)

    @property
    def state(self) -> str:
        if self.lat is None or self.lon is None:
            return "unresolved"
        if self.verified:
            return "verified"
        return "ingested" if self.source and self.source != "nominatim-runtime" else "resolved"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "water_body": self.water_body,
            "water_body_name": self.water_body_name,
            "lat": self.lat,
            "lon": self.lon,
            "state": self.state,
            "verified": self.verified,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "display_name": self.display_name,
            "has_ramp": self.has_ramp,
            "priority": self.priority,
        }


class SpotService:
    def __init__(self, data_dir: Path, dataset: str, geocoder: Geocoder | None = None) -> None:
        self._data_dir = data_dir
        self._dataset = dataset
        self._geocoder = geocoder
        self._spots: dict[str, Spot] = {}
        self._water_bodies: dict[str, dict] = {}
        self._warming = False
        self._load()

    # --- loading ----------------------------------------------------------

    def _load(self) -> None:
        seed_path = self._data_dir / "spots" / f"{self._dataset}.seed.json"
        ingested_path = self._data_dir / "spots" / f"{self._dataset}.json"

        if not seed_path.exists():
            raise FileNotFoundError(
                f"spot dataset not found: {seed_path}. "
                "Check SAILWISE_SPOTS_DATASET, or add a seed file."
            )

        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        for body in seed.get("water_bodies", []):
            self._water_bodies[body["id"]] = body

        for entry in seed.get("spots", []):
            body = self._water_bodies.get(entry.get("water_body") or "", {})
            self._spots[entry["id"]] = Spot(
                id=entry["id"],
                name=entry["name"],
                query=entry.get("query", entry["name"]),
                water_body=entry.get("water_body"),
                water_body_name=body.get("name"),
                timezone=body.get("timezone", "Europe/Rome"),
                priority=int(entry.get("priority", 3)),
            )

        # An ingested dataset, if present, overrides the seed with sourced values.
        if ingested_path.exists():
            ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
            for entry in ingested.get("spots", []):
                spot = self._spots.get(entry["id"])
                if spot is None or entry.get("lat") is None:
                    continue
                spot.lat = float(entry["lat"])
                spot.lon = float(entry["lon"])
                spot.source = entry.get("source", "osm")
                spot.retrieved_at = entry.get("retrieved_at")
                spot.display_name = entry.get("display_name")
                spot.verified = bool(entry.get("verified_by"))
                spot.facilities = entry.get("facilities") or {}
                launch = spot.facilities.get("launch_point")
                spot.has_ramp = None if launch is None else bool(launch)

    # --- access -----------------------------------------------------------

    def all(self) -> list[Spot]:
        return sorted(self._spots.values(), key=lambda s: (s.priority, s.name))

    def get(self, spot_id: str) -> Spot | None:
        return self._spots.get(spot_id)

    def water_bodies(self) -> list[dict]:
        return list(self._water_bodies.values())

    async def resolve(self, spot: Spot) -> Spot:
        """Fill in coordinates through the geocoder, once, and cache the result.

        Returns the spot unchanged when it already has coordinates, when geocoding is
        disabled, or when the lookup fails. A failed lookup leaves `lat`/`lon` as
        None — the spot stays unresolved rather than being placed somewhere plausible.
        """
        if spot.lat is not None or self._geocoder is None:
            return spot

        found = await self._geocoder.geocode(spot.query)
        if found is None:
            return spot

        lat, lon, display_name = found
        spot.lat = lat
        spot.lon = lon
        spot.display_name = display_name
        spot.source = "nominatim-runtime"
        spot.verified = False
        return spot

    async def resolve_many(self, spots: list[Spot]) -> list[Spot]:
        """Resolve sequentially: the public Nominatim policy is 1 request per second.

        Parallelising here would be faster and would also be an abuse of a service
        run on donated hardware. The disk cache means this cost is paid once.
        """
        for spot in spots:
            await self.resolve(spot)
        return spots

    def status(self) -> dict:
        spots = self.all()
        resolved = [s for s in spots if s.lat is not None]
        return {
            "total": len(spots),
            "resolved": len(resolved),
            "pending": len(spots) - len(resolved),
            "verified": sum(1 for s in resolved if s.verified),
            "warming": self._warming,
        }

    async def warm_up(self) -> None:
        """Resolve every unresolved spot in the background, in priority order.

        Geocoding 30-odd spots at one request per second takes about a minute, and
        blocking the first user request for that long would be a terrible way to meet
        the app. Instead this runs after startup: the highest-priority spots (Dervio,
        Colico, Torbole…) are available within seconds, the rest fill in, and the UI
        reports progress. The results are cached to disk, so this happens once ever
        rather than once per restart.
        """
        if self._geocoder is None:
            return
        self._warming = True
        try:
            for spot in self.all():
                if spot.lat is None:
                    await self.resolve(spot)
        finally:
            self._warming = False
