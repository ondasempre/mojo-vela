# 8–14, 26. System Architecture, Components, Data Flow, API, Python/Mojo split, Docker

## 8. System architecture

Four layers, one rule each.

```
┌──────────────────────────────────────────────────────────────────────┐
│  CLIENT           Web (later: mobile)                                │
│                   Renders plans. Contains no scoring logic.          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST/JSON over HTTPS
┌───────────────────────────────▼──────────────────────────────────────┐
│  APPLICATION      Python 3.12 + FastAPI                              │
│                   Orchestration, auth, validation, persistence,      │
│                   provider adapters, cache, assembly of plans.       │
│                   Owns all I/O. Owns no numerics.                    │
└───────┬───────────────────────┬──────────────────────┬───────────────┘
        │                       │                      │
┌───────▼────────┐   ┌──────────▼─────────┐   ┌────────▼──────────────┐
│  COMPUTE       │   │  PERSISTENCE       │   │  EXTERNAL             │
│  Mojo kernels  │   │  PostgreSQL +      │   │  Weather providers    │
│  scoring       │   │  PostGIS           │   │  Geocoding / POI      │
│  ranking       │   │  Redis (cache)     │   │  Routing              │
│  window search │   │                    │   │  LLM API              │
│  route eval    │   │                    │   │                       │
│  Pure numerics │   │                    │   │                       │
│  No I/O.       │   │                    │   │                       │
└────────────────┘   └────────────────────┘   └───────────────────────┘
```

**Why these technologies** (the brief asked for justification, so: no unexplained choices).

| Choice | Reason | Rejected alternative and why |
|---|---|---|
| Python + FastAPI | Async I/O suits a fan-out-to-providers workload; Pydantic gives schema validation that doubles as the API contract; it is the language the Mojo interop story is built around. | Django — too much framework for a JSON API with no server-rendered admin need. Node — would split the stack away from the Python↔Mojo interop path. |
| Mojo for compute | The ranking workload is a dense numeric map-reduce over uniform arrays: the exact shape SIMD and parallelism reward. Also the project's learning goal. | NumPy — genuinely a fair competitor and therefore the *benchmark baseline*, not a strawman (see [09](09-testing-benchmarks.md)). Rust — comparable performance, but no learning goal and a heavier interop boundary. |
| PostgreSQL + PostGIS | Spots, sessions and POIs are relational with geospatial queries ("within 100 km", "nearest launch"). PostGIS gives real spatial indexing instead of hand-rolled bounding boxes. | SQLite — fine for MVP 1 and in fact used there; PostGIS needed as soon as radius queries appear. MongoDB — the data is relational and would fight the model. |
| Redis | External-response cache with native TTL, plus rate-limit counters. | In-process cache — dies with the worker and cannot be shared. Postgres-as-cache — works, but TTL sweeping becomes homework. |
| Docker Compose | Reproducible local stack including the Mojo build image. | Kubernetes — unjustified before there are users. |
| REST | Simple, cacheable, trivially consumable; the shape of the data is request/response, not a graph. | GraphQL — the client fetches whole plans, not arbitrary field subsets. |

## 9. Component diagram

```
                         ┌────────────────────┐
                         │  API layer         │  FastAPI routers,
                         │  (routers/)        │  request/response schemas
                         └─────────┬──────────┘
                                   │ calls
                         ┌─────────▼──────────┐
                         │  Use-case services │  PlanService
                         │  (services/)       │  RankingService
                         │                    │  LogService
                         └───┬────────┬───────┘  ProfileService
             uses            │        │              uses
       ┌─────────────────────┘        └──────────────────────┐
┌──────▼─────────────┐                          ┌────────────▼─────────┐
│  Ports (abstract)  │                          │  Compute facade      │
│  WeatherProvider   │                          │  ComputeEngine       │
│  GeoProvider       │                          │   ├ MojoBackend      │
│  RoutingProvider   │                          │   └ PythonBackend    │
│  PoiProvider       │                          │  (identical results, │
│  Cache             │                          │   NFR-C-01)          │
│  Repositories      │                          └────────────┬─────────┘
└──────┬─────────────┘                                       │
       │ implemented by                                      │ FFI / CLI
┌──────▼──────────────────────────┐              ┌───────────▼──────────┐
│  Adapters (adapters/)           │              │  Mojo kernels        │
│  OpenMeteoProvider              │              │  wind stats          │
│  WindyProvider (key + terms)    │              │  score               │
│  NominatimGeoProvider           │              │  window search       │
│  OverpassPoiProvider            │              │  ranking sort        │
│  OsrmRoutingProvider            │              │  route evaluation    │
│  RedisCache / MemoryCache       │              └──────────────────────┘
│  SqlAlchemy repositories        │
└─────────────────────────────────┘
```

**The dependency rule:** services depend on ports; adapters depend on ports; nothing in `services/`
imports anything from `adapters/`. Wiring happens once, in the composition root. This is what makes
"swap Windy for another provider" a configuration change rather than a refactor.

## 10. Data flow — UC-1 "Where should I sail today?"

```
 user request (start, date, hours, driving limit, profile)
        │
        ▼
 [1] validate + resolve start location ─────────────► GeoProvider (cached 30d)
        │
        ▼
 [2] candidate spots: PostGIS radius query on spot table
        │
        ▼
 [3] for each candidate, in parallel:
        ├── forecast lookup ──► Cache ──hit──► normalised series (CACHED, age)
        │                        └─miss─► WeatherProvider ─► normalise ─► store
        └── static facilities from DB (source + retrieved_at)
        │
        ▼
 [4] build compute batch:  N spots × H hours × F fields  → contiguous float arrays
        │
        ▼
 [5] ComputeEngine.rank(batch, profile, prefs)   ← Mojo kernel (or Python fallback)
        │     returns per-spot: score, components, best window, wind stats
        ▼
 [6] safety pass (independent): gust / storm / visibility / trend gates → warnings[]
        │
        ▼
 [7] personal affinity from sailing log (shrunk to prior)
        │
        ▼
 [8] assemble ranked plans + provenance envelope + disclaimer
        │
        ▼
 response
```

Step **[4]** is the architectural hinge: it is where object graphs become flat numeric arrays. Doing
this conversion once, at the boundary, is what lets the compute core stay pure and vectorisable. Doing
it per-spot inside the loop would erase the benefit — a mistake worth naming in advance.

## 11. API design (v1)

Conventions: `/v1` prefix, `snake_case` JSON, RFC 9457 problem details for errors, ISO-8601 UTC
timestamps with explicit local-time fields where relevant, idempotent GETs.

Every response carries a provenance envelope:

```json
{
  "data": { },
  "meta": {
    "generated_at": "2026-08-15T06:12:03Z",
    "sources": [
      { "id": "open-meteo", "kind": "weather", "model": "icon-d2",
        "issued_at": "2026-08-15T03:00:00Z", "provenance": "FORECAST",
        "cache": { "state": "HIT", "age_s": 420, "ttl_s": 900 },
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)" }
    ],
    "disclaimer": "SailWise is decision support, not a safety clearance. Always check official forecasts and notices before departure."
  }
}
```

| Method | Path | Purpose | Milestone |
|---|---|---|---|
| GET | `/v1/health` | liveness/readiness | M4 |
| GET | `/v1/spots` | list/search spots (bbox, radius, facilities) | M4 |
| GET | `/v1/spots/{id}` | spot detail incl. facilities and provenance | M4 |
| GET | `/v1/weather?spot_id=&date=` | normalised hourly forecast | M4 |
| POST | `/v1/score` | score one spot for a window + profile | M4 |
| POST | `/v1/plan` | full plan for one spot | M4 |
| POST | `/v1/recommendations` | **the primary endpoint** — ranked spots | M4 |
| POST | `/v1/route/plan` | route proposal + along-route conditions | M8 |
| GET/POST | `/v1/sessions` | sailing log | M6 |
| GET | `/v1/spots/visited` | visited-spots aggregate | M6 |
| GET/PUT | `/v1/profile` | personal profile | M9 |
| GET/PUT | `/v1/profile/weights` | scoring profile weights | M9 |
| POST | `/v1/assistant/ask` | NL in, plan + explanation out | M10 |
| POST | `/v1/me/export`, `DELETE /v1/me` | GDPR export / erasure | M9 |

**`POST /v1/recommendations` — request:**

```json
{
  "origin": { "lat": null, "lon": null, "place": "Dervio" },
  "date": "2026-08-15",
  "available_hours": 5,
  "earliest_start": "09:00",
  "latest_return": "19:00",
  "max_driving_km": 100,
  "profile": "CRUISING",
  "boat": { "loa_m": 7.5, "type": "keelboat", "needs_ramp": true },
  "limit": 10
}
```

**Response (shape, values illustrative):**

```json
{
  "data": {
    "results": [
      {
        "spot": { "id": "dervio", "name": "Dervio" },
        "sailing_score": 88.4,
        "components": [
          { "id": "wind_quality",   "raw": 0.93, "weight": 0.30, "points": 27.9, "max_points": 30.0 },
          { "id": "wind_stability", "raw": 0.85, "weight": 0.20, "points": 17.0, "max_points": 20.0 }
        ],
        "best_window": { "start": "11:30", "end": "16:00", "confidence": "MEDIUM" },
        "wind": { "mean_kn": 11.2, "max_kn": 15.0, "max_gust_kn": 17.8,
                  "gust_factor": 1.28, "consistency": 0.81, "trend": "RISING_THEN_EASING" },
        "accessibility": { "score": 85, "driving": { "value": null, "provenance": "UNKNOWN" } },
        "affinity": { "score": 0.72, "sample_size": 14, "provenance": "USER" },
        "rank_score": 86.1,
        "warnings": [
          { "code": "GUST_ABOVE_LIMIT", "severity": "CAUTION", "from": "16:00",
            "message": "Gusts above your 18 kn limit expected after 16:00.",
            "recommendation": "Plan to be ashore by 15:30." }
        ],
        "is_recommended": true
      }
    ]
  },
  "meta": { }
}
```

Note `"driving": { "value": null, "provenance": "UNKNOWN" }` — before the routing adapter exists
(M7), the field is present and honestly empty rather than filled with a guess.

## 12. Python architecture

```
backend/
  app/
    main.py                 FastAPI app factory
    config.py               pydantic-settings; env only
    deps.py                 composition root — the only place adapters are named
    routers/                thin HTTP layer: parse, call service, serialise
    schemas/                pydantic request/response models (the API contract)
    domain/                 dataclasses + enums; no framework imports
      models.py  units.py  provenance.py  profiles.py  warnings.py
    services/               use cases; depend on ports only
      plan.py  ranking.py  log.py  profile.py  safety.py  assistant.py
    ports/                  Protocol/ABC definitions
      weather.py  geo.py  routing.py  poi.py  cache.py  repositories.py
    adapters/
      weather/open_meteo.py  weather/windy.py  weather/fixture.py
      geo/nominatim.py  poi/overpass.py  routing/osrm.py
      cache/redis_cache.py  cache/memory_cache.py
      db/                   SQLAlchemy models + repository implementations
    compute/
      engine.py             ComputeEngine facade + backend selection
      backend_python.py     reference implementation (the oracle)
      backend_mojo.py       Mojo binding
      batch.py              object graph → flat arrays
```

Rules: `domain/` imports nothing from the project's outer layers. `services/` never imports
`adapters/`. `compute/` never performs I/O. Async in routers and adapters; the compute path is
synchronous and offloaded to a thread/process pool so it cannot stall the event loop.

## 13. Mojo architecture

```
mojo/
  pixi.toml
  src/sailwise/
    units.mojo      conversions, clamp, trapezoid membership
    wind.mojo       Wind, WindStats
    weather.mojo    HourlyWeather, DayForecast
    spot.mojo       SailingSpot (compute-relevant subset)
    score.mojo      ScoreWeights, ScoreBreakdown, sailing_score
    window.mojo     best-window search               [M2]
    ranking.mojo    batch ranking + top-k            [M3]
    simd_kernels.mojo                                [M8 of learning path]
    parallel.mojo                                    [M9 of learning path]
    bindings.mojo   Python extension entry points    [M8+]
  tests/
  bench/
```

Design constraints on the Mojo side, chosen so the code stays optimisable:

1. **No I/O, no JSON, no networking.** Inputs arrive as numbers; results leave as numbers.
2. **Struct-of-arrays at the batch boundary.** `List[Float64]` of wind, of gust, of temperature —
   not `List[HourlyWeather]`. Vectorisation needs contiguous same-typed lanes; an array of structs
   would force a gather.
3. **Structs, not classes.** Value semantics, stack allocation, no reference counting on the hot path.
4. **Scalar-first, then optimise.** Every kernel ships as a correct scalar `fn` with tests, and only
   then gets a SIMD or parallel variant that must produce identical results (NFR-C-01).

**The Python↔Mojo boundary** is deliberately deferred and staged — see
[adr/0003](adr/0003-mojo-python-boundary.md). Summary: Milestone 1–3 run Mojo as a **CLI binary** with
a stable numeric contract (stdin/stdout), which is boring, debuggable and version-proof. The in-process
Python extension path (`mojo build --emit shared-lib` plus the Python import hook) is adopted later,
once benchmarks show the process boundary is the bottleneck — and it is worth noting that this interop
path is still described by Modular as early and evolving, which is exactly why it is not on the
critical path for MVP 1.

## 14. Docker architecture (§26)

```
docker/
  api.Dockerfile         python:3.12-slim, non-root, uv-installed deps
  mojo.Dockerfile        pixi + mojo; builds kernels; produces the binary/shared lib
  compose.yml            api, worker, postgres(+postgis), redis
  compose.dev.yml        overrides: hot reload, mounted source, fixture provider
```

Multi-stage: the Mojo image compiles kernels and the artefact is copied into the API image, so the
runtime image never carries a compiler. Postgres and Redis are pinned by digest. No secrets in images
— environment only. `docker compose up` is a required, tested path (NFR-M-03).
