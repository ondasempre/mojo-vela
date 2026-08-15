#!/usr/bin/env python3
"""Populate a sailing-spot dataset from OpenStreetMap, with provenance on every field.

    python3 scripts/fetch_spots.py --input  data/spots/lago_di_como.seed.json \
                                   --output data/spots/lago_di_como.json

What it does
    * geocodes each seed entry with Nominatim,
    * queries Overpass for facilities within a radius,
    * writes source, source_ref and retrieved_at for everything it fills,
    * leaves anything it could not source as null.

What it refuses to do
    * guess a coordinate,
    * fill a field without a source,
    * exceed the public services' usage policy.

Usage policy (see docs/06-integrations.md, checked 2026-08-15)
    The public Nominatim instance allows at most 1 request per second, requires an
    identifying User-Agent, and prohibits systematic or bulk querying. Overpass
    public instances support only a few hundred moderate queries per day. This
    script therefore rate-limits itself, identifies itself, and refuses to run on
    more than --max-spots entries.

    For a dataset of any real size, use a Geofabrik extract instead. That is what
    the OSM usage policy asks bulk consumers to do, and it is faster anyway.

Licence
    Output is derived from OpenStreetMap and is therefore ODbL: attribution to
    "© OpenStreetMap contributors" is required, and derived databases must be
    shared alike. See data/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

#: Required by the Nominatim usage policy: a real, identifying User-Agent with contact.
USER_AGENT = "SailWise/0.1 (open-source sailing planner; https://github.com/ondasempre/mojo-vela)"

#: The public policy limit is 1 request per second. We stay comfortably under it.
MIN_INTERVAL_S = 1.2

#: Refuse bulk use of the public endpoints.
DEFAULT_MAX_SPOTS = 15

OVERPASS_QUERY = """
[out:json][timeout:60];
(
  node(around:{radius},{lat},{lon})["leisure"="slipway"];
  way(around:{radius},{lat},{lon})["leisure"="slipway"];
  node(around:{radius},{lat},{lon})["leisure"="marina"];
  way(around:{radius},{lat},{lon})["leisure"="marina"];
  node(around:{radius},{lat},{lon})["amenity"="parking"];
  way(around:{radius},{lat},{lon})["amenity"="parking"];
  node(around:{radius},{lat},{lon})["amenity"~"^(restaurant|bar|cafe|fuel|drinking_water)$"];
  node(around:{radius},{lat},{lon})["club"="sailing"];
  way(around:{radius},{lat},{lon})["club"="sailing"];
);
out center tags;
"""

_last_request = 0.0


def throttled_get(url: str, data: bytes | None = None) -> dict:
    """One request, never faster than MIN_INTERVAL_S after the previous one."""
    global _last_request
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)

    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        _last_request = time.monotonic()
    return payload


def geocode(query: str) -> dict | None:
    url = f"{NOMINATIM}?{urllib.parse.urlencode({'q': query, 'format': 'json', 'limit': 1})}"
    results = throttled_get(url)
    if not results:
        return None
    hit = results[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "source": "nominatim",
        "source_ref": f"{hit.get('osm_type', '?')}/{hit.get('osm_id', '?')}",
        "display_name": hit.get("display_name"),
    }


def fetch_facilities(lat: float, lon: float, radius: int) -> dict:
    query = OVERPASS_QUERY.format(radius=radius, lat=lat, lon=lon)
    payload = throttled_get(OVERPASS, data=urllib.parse.urlencode({"data": query}).encode())

    buckets: dict[str, list[dict]] = {}
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        category = classify(tags)
        if category is None:
            continue
        centre = element.get("center", element)
        buckets.setdefault(category, []).append(
            {
                "name": tags.get("name"),
                "lat": centre.get("lat"),
                "lon": centre.get("lon"),
                "tags": {k: v for k, v in tags.items() if k in KEEP_TAGS},
                "source": "osm",
                "source_ref": f"{element.get('type')}/{element.get('id')}",
            }
        )
    return buckets


KEEP_TAGS = {
    "name", "opening_hours", "phone", "website", "fee", "access",
    "capacity", "surface", "parking", "cuisine", "amenity", "leisure", "club",
}


def classify(tags: dict) -> str | None:
    if tags.get("leisure") == "slipway":
        return "launch_point"
    if tags.get("leisure") == "marina":
        return "marina"
    if tags.get("club") == "sailing":
        return "sailing_clubs"
    amenity = tags.get("amenity")
    if amenity == "parking":
        return "parking"
    if amenity in {"restaurant", "bar", "cafe"}:
        return "restaurants"
    if amenity == "fuel":
        return "fuel"
    if amenity == "drinking_water":
        return "boat_services"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--radius", type=int, default=1500, help="POI search radius in metres")
    parser.add_argument("--max-spots", type=int, default=DEFAULT_MAX_SPOTS)
    parser.add_argument("--dry-run", action="store_true", help="geocode only, write nothing")
    args = parser.parse_args()

    seed = json.loads(args.input.read_text(encoding="utf-8"))
    spots = seed.get("spots", [])

    if len(spots) > args.max_spots:
        print(
            f"Refusing to run: {len(spots)} spots exceeds --max-spots={args.max_spots}.\n"
            "The public OSM endpoints are not for bulk use. Use a Geofabrik extract\n"
            "(https://download.geofabrik.de/europe/italy.html) for datasets of this size.",
            file=sys.stderr,
        )
        return 2

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_spots = []
    failures = 0

    for spot in spots:
        query = spot.get("query") or spot.get("name")
        print(f"geocoding {spot['id']}: {query}", file=sys.stderr)
        try:
            located = geocode(query)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  network error: {exc}", file=sys.stderr)
            located = None

        record = dict(spot)
        if located is None:
            # Unsourced stays unsourced. This is the whole point of the script.
            record["status"] = "ingestion_failed"
            failures += 1
            print("  not found — left null", file=sys.stderr)
            out_spots.append(record)
            continue

        record["lat"] = located["lat"]
        record["lon"] = located["lon"]
        record["source"] = located["source"]
        record["source_ref"] = located["source_ref"]
        record["retrieved_at"] = now
        record["display_name"] = located["display_name"]
        record["status"] = "ingested_unverified"

        if not args.dry_run:
            print(f"  facilities within {args.radius} m", file=sys.stderr)
            try:
                record["facilities"] = fetch_facilities(located["lat"], located["lon"], args.radius)
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"  overpass error: {exc} — facilities left null", file=sys.stderr)
                record["facilities"] = None

        out_spots.append(record)

    payload = {
        "dataset": seed.get("dataset"),
        "water_body": seed.get("water_body"),
        "generated_at": now,
        "generated_by": "scripts/fetch_spots.py",
        "licence": "ODbL — derived from OpenStreetMap",
        "attribution": "© OpenStreetMap contributors",
        "verification_note": "Records are 'ingested_unverified' until a human confirms the launch point is real, public and usable. See data/README.md.",
        "spots": out_spots,
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.output} ({len(out_spots)} spots, {failures} failed)", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
