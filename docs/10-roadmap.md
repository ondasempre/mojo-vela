# 29–30, 32–35. Repository Structure, Roadmap, MVPs, Future Features, Risks, Technical Debt

## 29. GitHub repository structure

Target layout (the repository grows into it; only what a milestone needs exists at that milestone):

```
sailwise/
├── README.md                  what it is, what it is not, quickstart
├── LICENSE                    MIT (code)
├── CONTRIBUTING.md
├── CHANGELOG.md
├── docker-compose.yml
├── .github/
│   ├── workflows/ci.yml  bench.yml  codeql.yml
│   └── ISSUE_TEMPLATE/  PULL_REQUEST_TEMPLATE.md
├── docs/                      this document set + ADRs + legal/
├── mojo/                      compute core
│   ├── pixi.toml
│   ├── src/sailwise/*.mojo
│   ├── tests/*.mojo
│   └── bench/*.mojo
├── backend/                   FastAPI application (from M4)
│   ├── pyproject.toml
│   └── app/{routers,schemas,domain,services,ports,adapters,compute}/
├── python/                    reference implementation + shared tooling
│   ├── pyproject.toml
│   └── src/sailwise_ref/
├── frontend/                  web client (from M6)
├── data/
│   ├── schemas/               JSON Schema for spots, forecasts, sessions
│   ├── spots/                 curated spot datasets (+ SOURCES.md)
│   ├── fixtures/              synthetic test data + golden outputs
│   └── contracts/             recorded provider payloads
├── benchmarks/                harness + results/
├── scripts/                   verify_env.sh, fetch_spots.py, gen_golden.py
├── docker/                    Dockerfiles
└── examples/                  runnable end-to-end examples
```

**Why `python/` and `backend/` are separate:** `python/` is the specification-following reference
implementation — the oracle for cross-language tests and the fallback compute backend. It has no web
dependencies and can be imported by benchmarks, tests and the backend alike. Merging it into
`backend/` would drag FastAPI into the test oracle for no reason.

Open-source hygiene from day one: MIT for code; a separate licence note for `data/` because
OSM-derived content is ODbL and share-alike; conventional commits; ADRs for decisions; issue and PR
templates; CI required for merge; `good first issue` labels for spot curation, which is the most
approachable contribution this project has.

## 30. Development roadmap — the first ten milestones

Each milestone is small enough to finish, ends with something runnable, and ends with tests. The
"Mojo level" column links to [mojo-learning-path.it.md](mojo-learning-path.it.md).

| # | Milestone | Deliverable | Mojo level | Done when |
|---|---|---|---|---|
| **M1** | **Environment + first structs + score v0** | `mojo/` project builds; `Wind`, `WindStats`, `ScoreWeights`, scalar `sailing_score`; Python reference; golden fixture | 1–2 | `mojo test` and `pytest` both pass; both implementations agree within 1e-9 |
| **M2** | Hourly series, best window, safety gates | `List`-based series processing; window search; warning catalogue | 3 | Window and warnings computed for the fixture day; safety tests pass |
| **M3** | Multi-spot ranking | Batch struct-of-arrays; ranking + top-k; accessibility from static data | 4–5 | 5 spots ranked from fixtures with a full explanation of the order |
| **M4** | Real weather + FastAPI | `WeatherProvider` port + Open-Meteo adapter; `/v1/weather`, `/v1/score`, `/v1/plan`, `/v1/recommendations`; SQLite persistence | — | A real forecast produces a real plan; contract tests green |
| **M5** | Cache + second provider | Redis cache with TTL/stale handling; optional Windy adapter behind a key | — | Cache hit/miss/stale visible in the API response; provider swap is config-only |
| **M6** | Sailing log + visited spots + first UI | Sessions, aggregates, and a web view that answers the Home question | — | An outing can be logged and appears on the visited-spots view |
| **M7** | Accessibility engine | Batch OSM ingestion → PostGIS; parking, launch, POI; driving estimates; Parking Score | 5 | Accessibility score computed from real, sourced data |
| **M8** | SIMD + route planner | SIMD kernels for stats/score/window; route graph and along-route evaluation | 6 | Benchmarks show a real margin over NumPy, and results are identical |
| **M9** | Parallel + personalisation | `parallelize()` ranking; explicit preferences; affinity with shrinkage; GDPR export/delete | 7 | 10k-spot ranking within budget; preferences change the ranking demonstrably |
| **M10** | Python↔Mojo in-process + AI assistant | Mojo as a Python extension module; NL → intent → engine → grounded explanation | 8–10 | Assistant answers the brief's example query with engine-produced numbers |

Milestone 1 is specified in detail in [milestone-1.md](milestone-1.md).

## 32. MVP definition

**MVP 1 — one spot, end to end** (M1–M4, plus a minimal view)

Input: location (Dervio), date, available hours, sailing profile.
Output: forecast, wind analysis, sailing score with breakdown, best window, safety warnings, one
spot's static info, a basic route suggestion, parking and food entries *where sourced data exists*,
cache indicators, and the ability to log the outing afterwards.

Out of scope for MVP 1: multiple spots, accounts, AI, mobile, real routing, live traffic.

The acceptance test is a sentence, not a checklist: *at 07:30 on a Saturday, the app answers "is it
worth going out at Dervio today, and when" faster and with more confidence than opening four other
apps.*

| Later MVP | Content |
|---|---|
| MVP 2 | Multiple spots and ranking (M3, M7) |
| MVP 3 | Accounts, personal profile, log-driven personalisation (M6, M9) |
| MVP 4 | Advanced routing with along-route conditions (M8) |
| MVP 5 | AI assistant (M10) |
| MVP 6 | Mobile (PWA first — it reuses the whole web client) |
| MVP 7 | Cloud deployment, multi-user, observability |
| MVP 8 | Community: contributed spots with review, open dataset publication |

## 33. Future features

Ordered by expected value per unit of effort, not by excitement:

1. **Forecast-quality scoring per spot and provider** — using the log's forecast-vs-observed pairs.
   Nobody else has this data for your spots. It also turns provider choice into a measurement.
2. **Thermal-regime modelling for lakes** — the Breva and Tivano on Lake Como are predictable
   thermal winds that global models resolve poorly; a local statistical correction trained on
   observations would be a genuine differentiator.
3. **Fetch-based wave estimation** — replaces the current `ESTIMATED` chop proxy with something
   physical (wind direction × exposed sector × fetch length).
4. **Multi-day planning** — "the best afternoon in the next five days".
5. **Group planning** — shared plans for a club or a crew.
6. **GPX import/export** — track import auto-fills a session; a strong log accelerator.
7. **Tide and current** for the marine extension — required before the Mediterranean rollout is
   credible.
8. **Webcam integration** — visual ground truth at the spot, subject to each provider's terms.
9. **Alerting** — "conditions at Dervio just moved into your band for Saturday".
10. **Open spot dataset** — publish the curated dataset under ODbL; the community contribution flywheel.

## 34. Risks

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | **Safety** — a user relies on the score and gets hurt | Severe | Low | Warnings independent of scoring; disclaimers everywhere; never claim safety; no route presented as navigational; conservative gate thresholds |
| R2 | Provider terms change or access is withdrawn | High | Medium | Port abstraction; ≥ 2 usable adapters; fixture provider always works; terms re-checked per release |
| R3 | Mojo is a young language; breaking changes | Medium | **High** | Pin the toolchain in `pixi.lock`; keep kernels small and dependency-free; **Python fallback is always shippable** (NFR-M-02); the CLI boundary insulates the backend from language-level churn |
| R4 | Mojo does not actually win on this workload | Low (technically) | Medium | Benchmark before adopting; NumPy is the honest baseline; a negative result is documented and kept — the learning goal survives either way |
| R5 | Scoring weights are subjective and disputed | Medium | High | Weights are configuration and versioned; scores stored with their model version; profiles let users disagree productively |
| R6 | Geodata quality (missing ramps, wrong parking) | Medium | High | Provenance per field; `UNKNOWN` is first-class; human verification flag; user corrections |
| R7 | Cost of provider APIs at scale | Medium | Medium | Cache-first architecture; geohash key collapsing; per-spot rather than per-user fetches |
| R8 | GDPR non-compliance | High | Low | Minimisation by schema; export/erasure from M9; consent separated for AI |
| R9 | Scope explosion (the brief is very large) | High | **High** | Milestones with hard exit criteria; MVP 1 deliberately narrow; features enter the roadmap, not the current milestone |
| R10 | Single-maintainer bus factor | Medium | High | Documentation-first; ADRs; small modules; contribution paths that need no Mojo knowledge |
| R11 | The Python↔Mojo in-process interop path is still evolving | Medium | Medium | Keep it off the critical path until M10; the CLI boundary works today ([adr/0003](adr/0003-mojo-python-boundary.md)) |

## 35. Technical debt strategy

**Debt that is deliberate and recorded** (each carries the milestone that repays it):

| Debt | Taken at | Repaid at |
|---|---|---|
| SQLite instead of PostGIS | M4 | M7 |
| Straight-line distances instead of road routing | M3 | M7 |
| Chop estimated from wind speed rather than fetch | M1 | M8+ |
| CLI process boundary instead of in-process FFI | M1 | M10, if benchmarks justify it |
| Spot dataset curated by hand | M3 | M7 batch ingestion |
| No auth (single local user) | M4 | M9 |

**The rules:**

1. Debt is written down when taken, with the milestone that repays it, in `docs/adr/` or in this
   table. Undocumented shortcuts are the only kind that compound.
2. Each milestone reserves ~20 % of its capacity for repayment. A milestone that repays nothing needs
   a reason.
3. Interfaces are never provisional. Implementations behind a port can be crude; the port itself is
   designed properly the first time, because that is what makes crude implementations replaceable.
4. `TODO` requires an issue number. `FIXME` fails lint.
5. A benchmark regression or a coverage drop is debt and blocks merge.
6. Deleting a feature is a legitimate way to repay its debt.
