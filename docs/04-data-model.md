# 11. Data Model and Database Schema

## Cross-cutting: provenance

Every externally-sourced or derived value carries a provenance class. This is the mechanism behind
rule 3 of the architecture and behind §29 of the brief ("never invent data").

| Class | Meaning | Example |
|---|---|---|
| `MEASURED` | Observation from an instrument/station | station wind at 10:00 |
| `FORECAST` | Model prediction for a future time | wind at 14:00 from ICON-D2 |
| `MODELLED` | Provider-side derived quantity | thunderstorm probability |
| `ESTIMATED` | **SailWise-derived** heuristic, not a physical measurement | lake chop from wind, boat speed from a simplified polar |
| `CACHED` | Any of the above served from cache (carries `age_s`) | — |
| `USER` | Supplied by the user | rating, notes, observed wind |
| `UNKNOWN` | Not available. Renders as "Unknown". | restaurant opening hours |

`UNKNOWN` is never coerced to a default. A missing facility does not score as absent; it lowers the
**confidence** attached to the score (FR-P-03).

```python
@dataclass(frozen=True)
class Sourced[T]:
    value: T | None
    provenance: Provenance
    source_id: str | None      # "open-meteo", "osm", "user"
    observed_at: datetime | None
    retrieved_at: datetime | None
    note: str | None           # e.g. "straight-line estimate, not road distance"
```

## Core entities

```
SailingSpot ──1:N── LaunchPoint
     │        ──1:N── Parking
     │        ──1:N── Poi (restaurant, bar, fuel, club, marina, shower, beach)
     │        ──1:N── SpotWindProfile   (typical/preferred wind by direction)
     │        ──1:N── SailingSession    (visits)
     │        ──1:N── SpotScoreSnapshot (historical computed scores)
     │
User ──1:1── UserProfile
     ──1:N── SailingSession
     ──1:N── VisitedSpotAggregate (materialised)
     ──1:N── FavoriteSpot
     ──1:N── ScoringWeightSet (custom profiles)

ForecastSnapshot ──1:N── HourlyForecast
CacheEntry (Redis primary, Postgres mirror for audit)
```

### SailingSpot

| Field | Type | Notes |
|---|---|---|
| `id` | text PK | slug, e.g. `dervio` |
| `name` | text | |
| `geom` | `geography(Point,4326)` | PostGIS; **NOT NULL** — a spot without verified coordinates is not ingested |
| `region`, `country` | text | ISO 3166-2 / -1 |
| `water_body_id` | FK | lake or sea basin |
| `water_type` | enum | `LAKE`, `SEA`, `LAGOON`, `RIVER` |
| `difficulty` | enum | `EASY`, `MODERATE`, `DEMANDING`, `UNKNOWN` |
| `typical_wind` | jsonb | thermal regime description, by season/hour; provenance-tagged |
| `preferred_wind_dir` | int[] | degrees; sectors that work well here |
| `exposure_sectors` | int[] | fetch-exposed sectors, used by the chop estimate |
| `facilities` | jsonb | booleans + `UNKNOWN`, each with source |
| `historical_score` | numeric | rolling mean of computed scores; derived |
| `source`, `source_ref`, `retrieved_at` | text/timestamptz | e.g. `osm`, `node/123456` |
| `verified_by`, `verified_at` | text/timestamptz | human verification of the coordinate |

### LaunchPoint

`id`, `spot_id`, `name`, `geom`, `kind` (`SLIPWAY`/`BEACH`/`CRANE`/`MARINA_HOIST`/`UNKNOWN`),
`surface`, `max_beam_m`, `fee`, `public_access` (tri-state), `notes`, `source`, `retrieved_at`.

### Parking

`id`, `spot_id`, `name`, `geom`, `distance_to_launch_m` (computed, `ESTIMATED` when straight-line),
`capacity`, `price_model` jsonb, `opening_hours` (OSM syntax), `payment_methods` text[],
`trailer_ok` tri-state, `source`, `retrieved_at`.

Tri-state booleans (`true` / `false` / `null = UNKNOWN`) are used throughout instead of defaulting to
`false` — "we don't know if trailers are allowed" and "trailers are not allowed" are different facts
and must not collapse.

### Poi

`id`, `spot_id`, `category` (`RESTAURANT`,`BAR`,`CAFE`,`GELATO`,`BEACH`,`SHOWER`,`FUEL`,
`BOAT_SERVICE`,`SAILING_CLUB`,`MARINA`), `name`, `geom`, `distance_m`, `opening_hours`,
`price_range`, `phone`, `website`, `rating` + `rating_source`, `source`, `retrieved_at`.

Ratings are only stored with an explicit `rating_source`. SailWise does not synthesise ratings.

### ForecastSnapshot / HourlyForecast

`ForecastSnapshot`: `id`, `spot_id`, `provider_id`, `model_id`, `issued_at`, `retrieved_at`,
`payload_hash`, `raw_payload` jsonb (retained only where the provider's terms permit storage).

`HourlyForecast`: `snapshot_id`, `valid_at`, and normalised fields —
`wind_kn`, `wind_dir_deg`, `gust_kn`, `temp_c`, `precip_mm`, `precip_prob`, `cloud_frac`,
`pressure_hpa`, `visibility_m`, `condition_code`, `storm_prob`, `wave_height_m` (nullable),
`wave_period_s` (nullable). Unique on `(snapshot_id, valid_at)`.

**Canonical units, enforced at the adapter boundary (FR-W-03):** wind in knots, direction in degrees
meteorological (the direction wind comes *from*), temperature °C, precipitation mm/h, probability
0–1, pressure hPa, visibility m, distance on water NM, distance on land km.

### SailingSession (the log)

`id`, `user_id`, `spot_id`, `date`, `start_time`, `end_time`, `route` (`geography(LineString)`,
nullable), `distance_nm`, `duration_min`, **forecast block** (`forecast_snapshot_id`,
`forecast_score`), **observed block** (`obs_wind_mean_kn`, `obs_wind_max_kn`, `obs_gust_max_kn`,
`obs_weather_note`, all `USER`), `user_rating` 1–10, `notes`, `visited_spot_ids` text[],
`created_at`.

Keeping forecast and observed side by side is what later makes provider quality measurable per spot
— an asset no competitor can copy from you.

### UserProfile

`user_id` PK, `wind_min_kn`, `wind_ideal_min_kn`, `wind_ideal_max_kn`, `wind_max_kn`,
`gust_limit_kn`, `duration_min_h`, `duration_max_h`, `max_driving_km`, `temp_min_c`, `temp_max_c`,
`default_profile`, `boat` jsonb, `units`, `locale`, `updated_at`.

All nullable, all user-editable, none inferred without confirmation (FR-L-05).

### VisitedSpotAggregate (materialised)

`user_id`, `spot_id`, `visit_count`, `last_visit`, `mean_rating`, `best_conditions` jsonb,
`worst_conditions` jsonb, `affinity` numeric (shrunk — see [05-algorithms.md](05-algorithms.md)).

### CacheEntry

Redis is authoritative; Postgres mirrors metadata for auditing and for the "where did this number
come from" view: `key`, `provider_id`, `data_class`, `params_hash`, `payload_hash`, `stored_at`,
`ttl_s`, `hit_count`, `last_served_at`, `stale_served_count`.

## Migrations and MVP simplification

MVP 1 runs on **SQLite + a JSON spot file**; PostGIS arrives with M7 when radius queries and real
distances appear. The domain dataclasses are storage-agnostic, so this is a repository swap. Alembic
owns migrations from M4 onward; before that the schema lives only in the JSON schema files under
`data/schemas/`.
