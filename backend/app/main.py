"""SailWise API + UI.

    uvicorn app.main:app --reload        (from backend/)
    ./scripts/run_local.sh              (from the repo root)

The composition root lives here: it is the only place that names concrete adapters
(ADR 0002). Everything else depends on the ports.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sailwise_ref.profiles import PROFILES, ProfileId, get_profile
from sailwise_ref.safety import DISCLAIMER

from .adapters.cache_memory import MemoryCache
from .adapters.events import CuratedEventsProvider, IcsEventsProvider
from .adapters.geo_nominatim import NominatimGeocoder
from .adapters.poi_overpass import OverpassPoiProvider
from .adapters.weather_fixture import FixtureWeatherProvider
from .adapters.weather_open_meteo import OpenMeteoProvider
from .adapters.webcams import CuratedWebcamProvider, WindyWebcamProvider
from .config import get_settings
from .services.images import ImageService
from .services.knowledge import KnowledgeService
from .services.places import PlacesService, category_metadata
from .services.planning import PlanningService
from .services.spots import SpotService

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Container:
    """Wiring. One place, constructed at startup, torn down at shutdown."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(follow_redirects=True)
        self.cache = MemoryCache()
        self.fixture = FixtureWeatherProvider()

        geocoder = (
            NominatimGeocoder(
                self.client,
                user_agent=self.settings.user_agent,
                cache_file=self.settings.geocode_cache_file,
                timeout_s=self.settings.http_timeout_s,
            )
            if self.settings.geocoding_enabled
            else None
        )

        self.spots = SpotService(
            data_dir=self.settings.data_dir,
            dataset=self.settings.spots_dataset,
            geocoder=geocoder,
        )

        if self.settings.weather_provider == "fixture":
            self.provider = self.fixture
        else:
            self.provider = OpenMeteoProvider(self.client, self.settings.http_timeout_s)

        # In "auto" the fixture provider is the fallback, so the app stays usable
        # offline. In "open-meteo" there is no fallback: failures surface, which is
        # what you want when you are testing the real integration.
        fallback = (
            self.fixture if self.settings.weather_provider in ("auto", "fixture") else self.provider
        )

        self.planning = PlanningService(
            spots=self.spots,
            provider=self.provider,
            fallback=fallback,
            cache=self.cache,
            forecast_ttl_s=self.settings.forecast_ttl_s,
            max_spots=self.settings.max_spots_per_request,
        )

        self.places = PlacesService(
            poi=OverpassPoiProvider(self.client, self.settings.user_agent),
            cache=self.cache,
            curated_webcams=CuratedWebcamProvider(self.settings.data_dir),
            curated_events=CuratedEventsProvider(self.settings.data_dir),
            windy_webcams=(
                WindyWebcamProvider(self.client, self.settings.windy_webcams_api_key)
                if self.settings.windy_webcams_api_key
                else None
            ),
            ics=IcsEventsProvider(self.client) if self.settings.ics_events_enabled else None,
            radius_m=self.settings.poi_radius_m,
        )
        self.planning.attach_places(self.places if self.settings.poi_enabled else None)
        self.images = ImageService(self.settings.data_dir)
        self.knowledge = KnowledgeService(self.settings.data_dir)

    async def aclose(self) -> None:
        await self.client.aclose()


container: Container | None = None


def deps() -> Container:
    if container is None:  # pragma: no cover - only reachable outside the lifespan
        raise RuntimeError("application not started")
    return container


@asynccontextmanager
async def lifespan(app: FastAPI):
    global container
    container = Container()
    # Resolve spot coordinates in the background so the first request is not held
    # for a minute behind a rate-limited geocoder.
    warmup = asyncio.create_task(container.spots.warm_up())
    yield
    warmup.cancel()
    await container.aclose()
    container = None


app = FastAPI(
    title="SailWise",
    version="0.2.0",
    summary="Intelligent sailing planner — decision support, not a safety clearance.",
    lifespan=lifespan,
)


# --- schemas ---------------------------------------------------------------


class RecommendationRequest(BaseModel):
    # Named `day`, not `date`: a field called `date` shadows the imported `date`
    # type inside the class body and breaks annotation evaluation.
    day: date | None = Field(default=None, description="defaults to today")
    profile: ProfileId = ProfileId.CRUISING
    origin_spot_id: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lon: float | None = Field(default=None, ge=-180, le=180)
    max_driving_km: float | None = Field(default=None, gt=0, le=2000)
    earliest_hour: int = Field(default=8, ge=0, le=23)
    latest_hour: int = Field(default=20, ge=0, le=23)
    min_duration_h: int = Field(default=3, ge=1, le=24)
    needs_ramp: bool = False
    gust_limit_kn: float | None = Field(default=None, gt=0, le=80)
    water_body: str | None = None
    limit: int = Field(default=8, ge=1, le=30)


# --- routes ----------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    c = deps()
    return {
        "status": "ok",
        "weather_provider": c.provider.id,
        "configured_mode": c.settings.weather_provider,
        "geocoding_enabled": c.settings.geocoding_enabled,
        "poi_enabled": c.settings.poi_enabled,
        "windy_webcams": bool(c.settings.windy_webcams_api_key),
        "spots": c.spots.status(),
        "cache": c.cache.stats(),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/profiles")
async def profiles() -> dict:
    return {
        "data": [
            {
                "id": p.id.value,
                "wind_band_kn": [
                    p.wind_band_kn.a, p.wind_band_kn.b, p.wind_band_kn.c, p.wind_band_kn.d,
                ],
                "temp_band_c": [
                    p.temp_band_c.a, p.temp_band_c.b, p.temp_band_c.c, p.temp_band_c.d,
                ],
                "gust_limit_kn": p.gust_limit_kn,
                "weights": {
                    "wind_quality": p.weights.wind_quality,
                    "wind_stability": p.weights.wind_stability,
                    "weather": p.weights.weather,
                    "rain": p.weights.rain,
                    "temperature": p.weights.temperature,
                    "water_conditions": p.weights.water_conditions,
                    "accessibility": p.weights.accessibility,
                },
            }
            for p in PROFILES.values()
        ]
    }


@app.get("/api/spots")
async def spots(water_body: str | None = None) -> dict:
    c = deps()
    items = [s for s in c.spots.all() if water_body is None or s.water_body == water_body]
    return {
        "data": {
            "spots": [s.as_dict() for s in items],
            "water_bodies": c.spots.water_bodies(),
        },
        "meta": {
            "attribution": "© OpenStreetMap contributors (coordinates, when resolved)",
            "note": (
                "Spots without coordinates have not been geocoded. They are listed, "
                "not placed approximately."
            ),
        },
    }


@app.post("/api/recommendations")
async def recommendations(request: RecommendationRequest) -> dict:
    c = deps()
    if request.latest_hour <= request.earliest_hour:
        raise HTTPException(422, "latest_hour must be after earliest_hour")

    origin = None
    if request.origin_lat is not None and request.origin_lon is not None:
        origin = (request.origin_lat, request.origin_lon)

    return await c.planning.recommend(
        profile=get_profile(request.profile),
        day=request.day or date.today(),
        origin_spot_id=request.origin_spot_id,
        origin=origin,
        max_driving_km=request.max_driving_km,
        earliest_hour=request.earliest_hour,
        latest_hour=request.latest_hour,
        min_duration_h=request.min_duration_h,
        needs_ramp=request.needs_ramp,
        gust_limit_kn=request.gust_limit_kn,
        water_body=request.water_body,
        limit=request.limit,
    )


@app.get("/api/spots/{spot_id}/plan")
async def plan(
    spot_id: str,
    profile: ProfileId = ProfileId.CRUISING,
    day: date | None = None,
    earliest_hour: int = Query(default=8, ge=0, le=23),
    latest_hour: int = Query(default=20, ge=0, le=23),
    min_duration_h: int = Query(default=3, ge=1, le=24),
) -> dict:
    c = deps()
    spot = c.spots.get(spot_id)
    if spot is None:
        raise HTTPException(404, f"unknown spot: {spot_id}")

    result = await c.planning.plan_for_spot(
        spot,
        get_profile(profile),
        day or date.today(),
        earliest_hour=earliest_hour,
        latest_hour=latest_hour,
        min_duration_h=min_duration_h,
    )
    if result["data"] is None:
        raise HTTPException(503, result.get("error") or "forecast unavailable")
    return result


@app.get("/api/spots/{spot_id}/places")
async def places(spot_id: str, refresh: bool = False) -> dict:
    """Parking (car and motorcycle), food, picnic areas, clubs and services.

    Fetched on demand for one spot rather than for every candidate in a ranking:
    Overpass is donated infrastructure and one query per candidate would be both slow
    and rude (see services/places.py).
    """
    c = deps()
    spot = c.spots.get(spot_id)
    if spot is None:
        raise HTTPException(404, f"unknown spot: {spot_id}")
    await c.spots.resolve(spot)
    if spot.lat is None:
        raise HTTPException(409, "this spot has no coordinates yet")

    if not c.settings.poi_enabled:
        return {
            "data": {"sections": [], "parking": None, "motorcycle_parking": None},
            "meta": {"disabled": True, "note": "POI lookup disabled (SAILWISE_POI=0)"},
        }

    result = await c.places.places_for(spot.lat, spot.lon, force=refresh)
    return {
        "data": {
            "spot": spot.as_dict(),
            "sections": c.places.sections_from(result),
            "parking": c.places.assess_parking(result).as_dict(),
            "motorcycle_parking": c.places.assess_parking(result, motorcycle=True).as_dict(),
            "total": len(result.places),
            "maps_url": (
                f"https://www.google.com/maps/search/?api=1&query={spot.lat:.6f},{spot.lon:.6f}"
            ),
            "directions_url": (
                f"https://www.google.com/maps/dir/?api=1&destination={spot.lat:.6f},{spot.lon:.6f}"
            ),
        },
        "meta": {
            "attribution": result.attribution,
            "retrieved_at": result.retrieved_at,
            "error": result.error,
            "radius_m": c.settings.poi_radius_m,
        },
    }


@app.get("/api/spots/{spot_id}/webcams")
async def webcams(spot_id: str) -> dict:
    c = deps()
    spot = c.spots.get(spot_id)
    if spot is None:
        raise HTTPException(404, f"unknown spot: {spot_id}")
    await c.spots.resolve(spot)
    if spot.lat is None:
        raise HTTPException(409, "this spot has no coordinates yet")

    result = await c.places.webcams_for(spot.lat, spot.lon, spot.water_body)
    return {
        "data": result.as_dict(),
        "meta": {
            "note": (
                "SailWise non pubblica webcam non verificate. Aggiungi le tue in "
                "data/webcams/webcams.json, oppure imposta WINDY_WEBCAMS_API_KEY."
            )
            if not result.webcams
            else None
        },
    }


@app.get("/api/events")
async def events(water_body: str | None = None) -> dict:
    c = deps()
    result = await c.places.events_for(water_body)
    return {"data": result.as_dict(), "meta": {"water_body": water_body}}


@app.get("/api/images")
async def images(water_body: str | None = None, spot_id: str | None = None) -> dict:
    """Photographs for the hero band and the spot gallery.

    Falls back to the built-in SVG illustrations, so there is always something to
    show and never a need for a borrowed placeholder.
    """
    c = deps()
    return {
        "data": c.images.as_dict(water_body=water_body, spot_id=spot_id),
        "meta": {
            "note": (
                "Nessuna fotografia nel manifest: mostro l'illustrazione inclusa. "
                "Aggiungi le tue in data/images/photos/ ed elencale in "
                "data/images/images.json — vedi data/images/README.md."
            )
            if not c.images.gallery(water_body, spot_id)
            else None
        },
    }


@app.get("/api/knowledge")
async def knowledge_index() -> dict:
    """The guides: winds, mooring, knots, safety."""
    c = deps()
    return {"data": {"topics": c.knowledge.available()}, "meta": {"problems": c.knowledge.problems}}


@app.get("/api/knowledge/{topic}")
async def knowledge_topic(topic: str, water_body: str | None = None) -> dict:
    c = deps()
    payload = c.knowledge.get(topic)
    if payload is None:
        raise HTTPException(404, f"unknown topic: {topic}")

    meta: dict = {}
    if topic == "winds" and water_body:
        # So the planner can deep-link "the winds of the lake you are looking at".
        meta["highlight"] = water_body
    return {"data": payload, "meta": meta}


@app.get("/api/categories")
async def categories() -> dict:
    """Emoji and labels for POI categories, so the UI keeps no second copy."""
    return {"data": category_metadata()}


@app.post("/api/cache/invalidate")
async def invalidate_cache(prefix: str | None = None) -> dict:
    """Manual invalidation (FR-C-06). Handy while developing against a live provider."""
    return {"data": {"removed": deps().cache.invalidate(prefix)}}


# --- UI --------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


@app.get("/photos/{filename:path}", include_in_schema=False)
async def photo(filename: str) -> FileResponse:
    """Serve a user photograph from the data directory.

    A route rather than a StaticFiles mount for two reasons: the directory may not
    exist yet at import time (and may change with SAILWISE_DATA_DIR), and the path
    is resolved and checked against its base on every request, so a crafted filename
    cannot climb out of the photos directory.
    """
    base = (deps().settings.data_dir / "images" / "photos").resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(404, "not found") from None
    if not candidate.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(candidate)


def main() -> None:  # pragma: no cover - entry point
    import uvicorn

    settings = get_settings()
    print(f"SailWise → http://{settings.host}:{settings.port}")
    print(f"  weather provider: {settings.weather_provider}")
    print(f"  today: {datetime.now().date().isoformat()}")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
