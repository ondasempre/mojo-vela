# 15–18. Weather Integration, Windy Strategy, Cache, Geospatial

> **Licensing is a design input, not paperwork done afterwards.** Every source below was checked for
> terms *before* being placed in the architecture (brief §29). Findings are dated; terms change, so
> re-verify before shipping and record the check in `docs/adr/`.
> **Verification date for everything on this page: 2026-08-15.**

## 15. Weather integration

### The port

```python
class WeatherProvider(Protocol):
    id: str
    async def hourly(self, lat: float, lon: float, day: date,
                     tz: str) -> ForecastSnapshot: ...
    def capabilities(self) -> ProviderCapabilities: ...
```

`ProviderCapabilities` declares which normalised fields the adapter can actually supply
(`waves: False` for an inland-only model, for example). The engine reads capabilities and marks
absent fields `UNKNOWN` — it never fills a gap with a default. This is the mechanism that makes
"support many providers" real rather than aspirational: consumers program against capabilities, not
against a particular provider's field list.

### Normalised model

```python
@dataclass(frozen=True)
class HourlyWeather:
    valid_at: datetime
    wind_kn: float; wind_dir_deg: float; gust_kn: float
    temp_c: float; precip_mm: float; precip_prob: float
    cloud_frac: float; pressure_hpa: float; visibility_m: float
    condition: ConditionCode; storm_prob: float
    wave_height_m: float | None; wave_period_s: float | None
```

Unit conversion (m/s → kn, mm → mm/h, % → 0–1) happens **in the adapter**. The engine sees canonical
units only (FR-W-03). Every adapter ships a unit round-trip test.

### Provider comparison

| Provider | Access | Licence / terms (checked 2026-08-15) | Role in SailWise |
|---|---|---|---|
| **Open-Meteo** | Free HTTP API, no key for the non-commercial tier | Free tier is **non-commercial use only**, up to **10,000 calls/day**; data under **CC BY 4.0**, attribution required; paid plans for commercial use and higher volume | **Default adapter.** Fits an open-source, non-commercial project exactly, and the attribution requirement is easy to honour. |
| **Windy Point Forecast API** | `POST https://api.windy.com/api/point-forecast/v2`, API key required | Trial version is **for development purposes only**; the Professional version is a paid annual subscription; the community guidance is that using the API to build a *weather application* falls outside the standard terms. Daily limits are raised only by explicit agreement. | **Optional adapter, key-gated, off by default.** See the strategy below. |
| **National services** (e.g. ARPA Lombardia for Lake Como, national met services) | Varies; often open data | Per-source; several Italian regional agencies publish open data with attribution | Candidate for `MEASURED` station observations, which is data no forecast model gives you. High value for the forecast-vs-observed comparison (§04 data model). |
| **Fixture provider** | Local JSON | n/a — synthetic | Tests, demos, offline development, CI. Always available. |

### Ranking of provider work

1. `FixtureWeatherProvider` (M1–M3) — deterministic, no network, makes the whole engine testable.
2. `OpenMeteoProvider` (M4) — the first real data.
3. Observation adapters (M6+) — enables forecast-quality measurement.
4. `WindyProvider` (M5, optional) — only with a key the user supplies and a terms check.

## 16. Windy integration strategy

The brief names Windy as the conceptual reference. The honest engineering answer, given what the
terms actually say:

**What SailWise will do:**

- **Treat Windy as one adapter behind `WeatherProvider`, never as the architecture.** Nothing in the
  domain model, the engine or the API mentions Windy.
- **Ship the adapter disabled.** It activates only when the operator supplies `WINDY_API_KEY`, and
  the configuration flag is named `WINDY_ENABLED_I_HAVE_CHECKED_THE_TERMS` — deliberately awkward,
  because the operator, not the library, carries the licence obligation.
- **Respect the trial's stated purpose.** The trial tier is documented as development-only, so it is
  used for development only. A deployed public instance requires the Professional subscription, or it
  runs on Open-Meteo.
- **Use Windy's embeddable map/widget for *visualisation*** rather than pulling map tiles through an
  API path they are not offered under. Visual reference (the brief's real ask — "use Windy as the
  reference") is satisfiable without a data licence.
- **Cache aggressively and honour rate limits** — one point-forecast call per (spot, model, issue
  cycle), never per user request.

**What SailWise will not do:**

- No scraping of `windy.com`. A web page is not an API (brief §29), and scraping against terms is out
  of scope permanently, not "until we need it".
- No redistribution of Windy payloads through the public SailWise API.
- No claim of affiliation or endorsement.

**Consequence for the roadmap:** the default public deployment runs Open-Meteo with visible CC BY
attribution. Windy becomes attractive when the project wants premium models (ECMWF, high-res
regional) and someone is paying for the subscription. Because of the port, that day is a config
change. This is [adr/0002](adr/0002-weather-provider-abstraction.md).

## 17. Cache architecture

### Key design

```
sw:{version}:{data_class}:{provider}:{geohash6}:{param_hash}:{time_bucket}
```

- `geohash6` ≈ 1.2 km cells — forecasts do not differ meaningfully inside one, and rounding
  coordinates before they become a key is what turns thousands of near-identical requests into one.
  It is also a privacy measure: precise user coordinates never enter a cache key.
- `param_hash` = SHA-256 of the sorted request parameters (model, fields, units), truncated.
- `time_bucket` = the forecast issue cycle, not the wall clock, so a cache entry naturally expires
  when the model updates rather than on an arbitrary timer.
- `version` lets a schema change invalidate everything atomically.

### TTLs (FR-C-03)

| Data class | TTL | Rationale |
|---|---|---|
| Weather forecast | 15 min (or until the next model cycle, whichever is sooner) | Matches the brief; model output does not change faster than its issue cycle. |
| Station observations | 5 min | |
| Traffic / driving time | 10 min | Only meaningful near the time of travel. |
| Geocoding | 30 days | Place coordinates are effectively static. |
| Parking metadata | 6 h | |
| POI / restaurants | 24 h | |
| Sailing spots (static) | 7 days | |
| Tiles / basemap | per provider terms | |
| Sailing log, aggregates | persistent | Owned data, not cached data. |

### Entry contents (FR-C-02)

`key`, `provider_id`, `data_class`, `payload` (or a pointer), `payload_hash`, `stored_at`, `ttl_s`,
`request_params`, `provenance`, `hit_count`.

### Behaviour

- **Hit:** serve, mark `CACHED`, report `age_s`.
- **Miss:** fetch, normalise, store, serve as `FORECAST`/`MEASURED`.
- **Expired + provider healthy:** stale-while-revalidate — serve stale marked `STALE` and refresh in
  the background.
- **Expired + provider down:** serve stale marked `STALE` with age (FR-C-05). If nothing is cached,
  return an error. **Never** fabricate (NFR-R-03).
- **Payload hash unchanged on refresh:** extend the TTL without rewriting — cheap, and it makes
  "the model has not updated yet" observable.
- **Invalidation:** by key, by provider, by spot, and globally via the version prefix.
- **Negative caching:** provider errors are cached for 60 s to avoid hammering a failing service.

The UI requirement is explicit (FR-C-04): a cached figure shows its age. "11 kn · Open-Meteo ·
7 min ago" is a very different statement from "11 kn".

### Storage layout

Redis primary (native TTL, shared across workers), Postgres mirror of metadata only, for the "where
did this number come from" audit view. Raw payloads are persisted only where the provider's terms
allow retention — another reason the licence table above exists.

## 18. Geospatial architecture

### Data sources

| Need | Source | Terms (checked 2026-08-15) |
|---|---|---|
| Geocoding place → coordinates | **Nominatim** (OSM) | Public instance: **max 1 req/s**, no heavy or systematic use, a valid identifying `User-Agent` is required, no auto-complete against the public endpoint; applications whose *primary* function is geocoding must self-host. Data is **ODbL** — attribution required, share-alike on derived databases. |
| POIs (parking, ramps, restaurants, clubs) | **Overpass API** (OSM) | Public instances support only a few hundred moderate queries per day; heavy use must be self-hosted or use extracts. ODbL. |
| Bulk spot ingestion | **Geofabrik extracts** (Lombardia / Italia) | The correct answer for anything systematic — the OSM policy explicitly directs bulk consumers to extracts rather than the live APIs. |
| Road routing / driving time | **OSRM** (self-hosted or a public demo server for development only) or a commercial API | OSRM software is BSD; the demo server is not for production. |
| Basemap tiles | A tile provider under its own terms | The OSM Foundation tile servers are **not** for heavy application use. |

**Design consequence:** SailWise **ingests geodata in batch, ahead of time** into its own PostGIS
database, and does not call OSM APIs on the user request path. That is simultaneously the
policy-compliant design, the fast design and the offline-tolerant design. Live geocoding is used only
for one-off user-typed place lookups, rate-limited to 1 req/s with a 30-day cache.

**Attribution obligations, honoured in-product:** "© OpenStreetMap contributors" wherever OSM-derived
data is shown; "Weather data by Open-Meteo.com (CC BY 4.0)" wherever forecast data is shown. Derived
databases published by the project inherit ODbL share-alike — which is why `data/` carries its own
licence note separate from the code licence.

### Spatial queries

PostGIS `geography(Point,4326)`:

- candidates within a driving limit: `ST_DWithin(spot.geom, origin, radius_m)` with a radius inflated
  by a **detour factor of 1.35** (roads are not straight lines), then refined by the routing adapter;
- nearest launch / parking / POI: `ST_Distance` with a GiST index;
- along-route conditions: `ST_LineInterpolatePoint` at each leg's midpoint;
- the water path check for routes: `ST_Contains(water_polygon, leg_line)`.

Until PostGIS arrives (M7), the same queries run as haversine in Python over a small in-memory spot
list, behind the same repository interface. Same contract, smaller engine.

### Coordinate integrity rule

A spot without a coordinate verified against a named source is **not ingested**. There is no
"approximate location" state. This is why `data/spots/` in this repository ships a schema and an
ingestion script instead of a table of latitudes — the environment that produced this design had no
access to OSM, and writing plausible coordinates from memory would have been exactly the failure mode
the brief prohibits.
