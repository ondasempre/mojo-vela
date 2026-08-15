# 6–7. Functional and Non-Functional Requirements

Requirement IDs are stable and referenced from tests. `MUST` / `SHOULD` / `MAY` per RFC 2119.

## 6. Functional Requirements

### FR-W — Weather

| ID | Requirement | Milestone |
|---|---|---|
| FR-W-01 | The system MUST obtain hourly forecasts through a `WeatherProvider` port, with at least one working adapter. | M4 |
| FR-W-02 | The normalised forecast MUST carry: wind speed, wind direction, wind gust, temperature, precipitation amount, precipitation probability, cloud cover, pressure, visibility, condition code, thunderstorm probability. Wave height and period are OPTIONAL and MUST be `UNKNOWN` when the provider does not supply them. | M4 |
| FR-W-03 | All wind speeds MUST be stored in knots and all distances on water in nautical miles; conversion happens in the adapter, never in the engine. | M1 |
| FR-W-04 | Every forecast value MUST carry provenance (provider id, model id when known, issue time, valid time, provenance class). | M4 |
| FR-W-05 | The system MUST support more than one provider simultaneously and MUST allow per-spot provider preference. | M5 |
| FR-W-06 | When providers disagree beyond a configured threshold, the system SHOULD surface the disagreement rather than silently picking one. | M9 |

### FR-S — Scoring

| ID | Requirement | Milestone |
|---|---|---|
| FR-S-01 | The system MUST compute a Sailing Score in [0, 100] for a (spot, window, profile) triple. | M1 |
| FR-S-02 | The score MUST decompose into named components, each with its own raw sub-score, weight and contribution. | M1 |
| FR-S-03 | Component weights MUST be configuration, not code, and MUST be per-profile. | M1 |
| FR-S-04 | Profiles RELAX, CRUISING, TRAINING, RACING, FAMILY, SPORT MUST be supported. | M1 |
| FR-S-05 | Weights within a profile MUST be normalised to sum to 1 before use; a profile whose weights do not sum to 1 MUST be accepted and normalised, not rejected. | M1 |
| FR-S-06 | Scoring MUST be deterministic: identical inputs produce bit-identical outputs. | M1 |
| FR-S-07 | The system MUST compute the best contiguous sailing window of at least the user's minimum duration. | M2 |
| FR-S-08 | The system MUST identify unsuitable periods and mark the reason. | M2 |
| FR-S-09 | Wind statistics MUST include mean, max, max gust, standard deviation, gust factor, consistency and trend. | M1 |

### FR-R — Ranking

| ID | Requirement | Milestone |
|---|---|---|
| FR-R-01 | The system MUST rank candidate spots for a given request. | M3 |
| FR-R-02 | Ranking MUST apply hard filters (driving limit, required facilities) before scoring. | M3 |
| FR-R-03 | Ranking MUST combine sailing score, accessibility and personal affinity with documented weights. | M3 |
| FR-R-04 | Ranking MUST work with an empty user history (cold start). | M3 |
| FR-R-05 | The system MUST be able to explain a pairwise ordering in terms of component deltas. | M3 |

### FR-P — Spots, parking, services

| ID | Requirement | Milestone |
|---|---|---|
| FR-P-01 | Each spot MUST follow the `SailingSpot` schema in [04-data-model.md](04-data-model.md). | M1 |
| FR-P-02 | Spot data MUST record source and retrieval timestamp per field group. | M3 |
| FR-P-03 | Missing facility data MUST be represented as `UNKNOWN` and MUST NOT be scored as either present or absent — it MUST reduce confidence, not the score. | M3 |
| FR-P-04 | The system MUST compute a Parking Score from distance, availability, cost and constraints. | M7 |
| FR-P-05 | The system MUST list nearby food and services with category, distance, hours, contact — each field independently nullable. | M7 |
| FR-P-06 | The system MUST NOT display commercial data (price, hours, rating) without a source attribution. | M7 |

### FR-A — Accessibility / driving

| ID | Requirement | Milestone |
|---|---|---|
| FR-A-01 | The system MUST estimate driving distance and time from the user's start point. | M7 |
| FR-A-02 | Driving estimates MUST be labelled with their method (straight-line estimate vs routing provider). | M7 |
| FR-A-03 | The system MUST compute an Accessibility Score in [0, 100]. | M3 |

### FR-C — Cache

| ID | Requirement | Milestone |
|---|---|---|
| FR-C-01 | All external responses MUST pass through the cache layer. | M5 |
| FR-C-02 | Cache entries MUST store: key, provider, payload hash, stored-at, TTL, and the request parameters that produced them. | M5 |
| FR-C-03 | TTLs MUST be per data class and configurable (see [06-integrations.md](06-integrations.md)). | M5 |
| FR-C-04 | Cache-sourced values MUST be marked `CACHED` with their age, and the UI MUST show it. | M5 |
| FR-C-05 | Expired entries MAY be served as `STALE` when the provider is unreachable, and MUST be visibly marked. | M5 |
| FR-C-06 | Cache MUST support explicit invalidation by key, by provider and by spot. | M5 |

### FR-L — Log and personalisation

| ID | Requirement | Milestone |
|---|---|---|
| FR-L-01 | The system MUST persist sailing sessions per the `SailingSession` schema. | M6 |
| FR-L-02 | A session MUST distinguish forecast conditions from observed conditions. | M6 |
| FR-L-03 | Visited spots MUST aggregate visit count, last visit, mean rating, best/worst conditions. | M6 |
| FR-L-04 | The personal profile MUST be explicitly editable. | M9 |
| FR-L-05 | Derived preference changes MUST be proposed and confirmed, never auto-applied. | M9 |
| FR-L-06 | Personal affinity MUST be shrunk toward a prior when the sample is small. | M9 |

### FR-Z — Safety

| ID | Requirement | Milestone |
|---|---|---|
| FR-Z-01 | Safety warnings MUST be produced by a pipeline independent of scoring. | M2 |
| FR-Z-02 | A high score MUST NOT suppress, hide or downgrade a warning. | M2 |
| FR-Z-03 | Warnings MUST have severity INFO / CAUTION / CRITICAL and a machine-readable code. | M2 |
| FR-Z-04 | Every plan output MUST carry the disclaimer that official sources take precedence. | M2 |
| FR-Z-05 | The system MUST NOT present the score as a safety clearance anywhere in copy or UI. | M2 |

### FR-X — AI assistant

| ID | Requirement | Milestone |
|---|---|---|
| FR-X-01 | The assistant MUST obtain all figures from the deterministic engine. | M10 |
| FR-X-02 | The assistant MUST NOT alter scores, rankings or warnings. | M10 |
| FR-X-03 | Assistant output MUST be reproducible from the engine payload it was given (the payload is logged with the answer). | M10 |
| FR-X-04 | If intent extraction is ambiguous, the assistant MUST ask rather than assume. | M10 |

## 7. Non-Functional Requirements

### Performance

| ID | Requirement |
|---|---|
| NFR-P-01 | `POST /v1/plan` for a single spot with warm cache: p95 < 300 ms server-side. |
| NFR-P-02 | Ranking 50 spots with warm cache: p95 < 800 ms server-side. |
| NFR-P-03 | Scoring compute itself (excluding I/O) MUST be < 10 % of request latency at 50 spots — this is the measurement that justifies the Mojo core, and it is a *test*, not an assumption. |
| NFR-P-04 | Ranking MUST scale to 5,000 spots for national coverage within 2 s of compute on a 4-core machine. |
| NFR-P-05 | Cold cache latency is bounded by providers; the UI MUST stream partial results rather than block. |

### Correctness

| ID | Requirement |
|---|---|
| NFR-C-01 | The Mojo engine and the Python reference MUST agree within 1e-9 on the golden fixtures. This is a CI gate. |
| NFR-C-02 | Unit test line coverage of scoring and ranking ≥ 90 %. |
| NFR-C-03 | Every algorithm constant MUST be named and documented; magic numbers in code are a review blocker. |

### Reliability

| ID | Requirement |
|---|---|
| NFR-R-01 | A provider outage MUST degrade to cache, not to error. |
| NFR-R-02 | Provider calls MUST have timeouts, bounded retries with backoff, and a circuit breaker. |
| NFR-R-03 | The system MUST never emit a fabricated value in place of a failed fetch. |

### Security & privacy

| ID | Requirement |
|---|---|
| NFR-S-01 | Secrets from environment/secret manager only; never in the repository. A secret scanner runs in CI. |
| NFR-S-02 | Authenticated endpoints for anything user-specific; per-user data isolation enforced at the query layer. |
| NFR-S-03 | Personal data minimised — see [08-security-privacy.md](08-security-privacy.md). |
| NFR-S-04 | Full export and hard delete of user data MUST be supported. |

### Maintainability & portability

| ID | Requirement |
|---|---|
| NFR-M-01 | No business logic in adapters; no I/O in the compute core. The compute core MUST be pure functions over plain numeric arrays. |
| NFR-M-02 | The system MUST run with the Mojo core disabled (Python fallback), so that a Mojo toolchain regression cannot block the product. |
| NFR-M-03 | `docker compose up` MUST bring up a working local stack. |
| NFR-M-04 | Every external dependency MUST have its licence and terms recorded in [06-integrations.md](06-integrations.md) before integration. |

### Usability & accessibility

| ID | Requirement |
|---|---|
| NFR-U-01 | Home answers "where should I sail today?" above the fold, without input, using defaults. |
| NFR-U-02 | Every score is expandable into its components in one interaction. |
| NFR-U-03 | Colour MUST NOT be the only carrier of warning severity (WCAG 2.2 AA). |
| NFR-U-04 | Units (kn, NM, °C, km) MUST be explicit on every figure. |
