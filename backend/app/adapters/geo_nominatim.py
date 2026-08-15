"""Nominatim geocoder for one-off, user-triggered place lookups.

Usage policy (checked 2026-08-15, docs/06-integrations.md): the public instance
allows **at most 1 request per second**, requires an identifying **User-Agent**, and
prohibits systematic or bulk querying — applications whose primary function is
geocoding must self-host.

This adapter therefore:

* serialises requests behind a lock with a minimum interval,
* sends the configured User-Agent,
* caches aggressively (30 days) and persists the cache to disk, so a spot is
  geocoded once ever rather than once per restart,
* returns None on failure. It never approximates a location.

For anything beyond resolving a handful of curated spots, use a Geofabrik extract
and `scripts/fetch_spots.py` — that is what the policy asks bulk consumers to do.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

ENDPOINT = "https://nominatim.openstreetmap.org/search"

#: The policy limit is 1 req/s; stay comfortably under it.
MIN_INTERVAL_S = 1.2

ATTRIBUTION = "© OpenStreetMap contributors"


class NominatimGeocoder:
    id = "nominatim"

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        cache_file: Path | None = None,
        timeout_s: int = 20,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._cache_file = cache_file
        self._timeout_s = timeout_s
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._cache: dict[str, dict] = self._load_cache()

    def _load_cache(self) -> dict[str, dict]:
        if self._cache_file and self._cache_file.exists():
            try:
                return json.loads(self._cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cache(self) -> None:
        if not self._cache_file:
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # a non-writable cache must not break the request

    def cached(self, query: str) -> tuple[float, float, str] | None:
        hit = self._cache.get(query)
        if hit is None:
            return None
        return hit["lat"], hit["lon"], hit["display_name"]

    async def geocode(self, query: str) -> tuple[float, float, str] | None:
        hit = self.cached(query)
        if hit is not None:
            return hit

        async with self._lock:
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._client.get(
                    ENDPOINT,
                    params={"q": query, "format": "json", "limit": 1},
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout_s,
                )
                response.raise_for_status()
                results = response.json()
            except (httpx.HTTPError, ValueError):
                return None
            finally:
                self._last_request = time.monotonic()

        if not results:
            return None

        first = results[0]
        record = {
            "lat": float(first["lat"]),
            "lon": float(first["lon"]),
            "display_name": first.get("display_name", query),
            "source": "nominatim",
            "source_ref": f"{first.get('osm_type', '?')}/{first.get('osm_id', '?')}",
        }
        self._cache[query] = record
        self._save_cache()
        return record["lat"], record["lon"], record["display_name"]
