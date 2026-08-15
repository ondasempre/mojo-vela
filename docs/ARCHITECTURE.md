# SailWise — Software Architecture & Development Plan

> **Status:** design baseline, v0.1 (2026-08-15)
> **Scope of this document set:** the full architecture plan requested in the project brief.
> It is a *plan*, not a description of shipped software. Milestone 1 is the only part with code in the repository today.

## How this document set is organised

The brief asked for 35 deliverables. They are grouped into ten documents so that each one stays
readable and independently reviewable.

| # | Brief section | Document |
|---|---|---|
| 1 | Executive Summary | [01-product-vision.md](01-product-vision.md) |
| 2 | Product Vision | [01-product-vision.md](01-product-vision.md) |
| 3 | Personas | [01-product-vision.md](01-product-vision.md) |
| 4 | User Stories | [01-product-vision.md](01-product-vision.md) |
| 5 | Use Cases | [01-product-vision.md](01-product-vision.md) |
| 6 | Functional Requirements | [02-requirements.md](02-requirements.md) |
| 7 | Non-Functional Requirements | [02-requirements.md](02-requirements.md) |
| 8 | System Architecture | [03-system-architecture.md](03-system-architecture.md) |
| 9 | Component Diagram | [03-system-architecture.md](03-system-architecture.md) |
| 10 | Data Flow Diagram | [03-system-architecture.md](03-system-architecture.md) |
| 11 | Database Schema | [04-data-model.md](04-data-model.md) |
| 12 | API Design | [03-system-architecture.md](03-system-architecture.md) |
| 13 | Mojo Architecture | [03-system-architecture.md](03-system-architecture.md), [adr/0003](adr/0003-mojo-python-boundary.md) |
| 14 | Python Architecture | [03-system-architecture.md](03-system-architecture.md) |
| 15 | Weather Integration | [06-integrations.md](06-integrations.md) |
| 16 | Windy Integration Strategy | [06-integrations.md](06-integrations.md), [adr/0002](adr/0002-weather-provider-abstraction.md) |
| 17 | Cache Architecture | [06-integrations.md](06-integrations.md) |
| 18 | Geospatial Architecture | [06-integrations.md](06-integrations.md) |
| 19 | Sailing Score Algorithm | [05-algorithms.md](05-algorithms.md) |
| 20 | Ranking Algorithm | [05-algorithms.md](05-algorithms.md) |
| 21 | Route Planning Algorithm | [05-algorithms.md](05-algorithms.md) |
| 22 | Personalization Engine | [05-algorithms.md](05-algorithms.md) |
| 23 | AI Architecture | [07-ai-layer.md](07-ai-layer.md) |
| 24 | Security | [08-security-privacy.md](08-security-privacy.md) |
| 25 | Privacy / GDPR | [08-security-privacy.md](08-security-privacy.md) |
| 26 | Docker Architecture | [03-system-architecture.md](03-system-architecture.md) |
| 27 | Testing Strategy | [09-testing-benchmarks.md](09-testing-benchmarks.md) |
| 28 | Benchmark Strategy | [09-testing-benchmarks.md](09-testing-benchmarks.md) |
| 29 | GitHub Repository Structure | [10-roadmap.md](10-roadmap.md) |
| 30 | Development Roadmap | [10-roadmap.md](10-roadmap.md) |
| 31 | Mojo Learning Roadmap | [mojo-learning-path.it.md](mojo-learning-path.it.md) |
| 32 | MVP Definition | [10-roadmap.md](10-roadmap.md) |
| 33 | Future Features | [10-roadmap.md](10-roadmap.md) |
| 34 | Risks | [10-roadmap.md](10-roadmap.md) |
| 35 | Technical Debt Strategy | [10-roadmap.md](10-roadmap.md) |

Architecture Decision Records live in [adr/](adr/). They record *why*, not *what*.

## The five rules this architecture is built on

These are load-bearing. Every design decision downstream can be traced to one of them.

1. **Python orchestrates, Mojo computes.** Mojo is used where a measurement justifies it, never
   because it is the project's mascot language. See [adr/0001](adr/0001-hybrid-python-mojo.md).
2. **No provider lock-in.** Every external data source sits behind a port (interface). Windy is one
   adapter among several, and it is *not* the default one, for licensing reasons documented in
   [adr/0002](adr/0002-weather-provider-abstraction.md).
3. **Every number carries its provenance.** A value is `MEASURED`, `FORECAST`, `MODELLED`,
   `ESTIMATED`, `CACHED`, `USER` or `UNKNOWN`. The UI must show it. `UNKNOWN` is a legitimate,
   first-class answer — inventing a plausible value is a defect, not a convenience.
4. **The score is advice, never a safety clearance.** Scoring and safety warnings are two separate
   pipelines with separate outputs. A high score never suppresses a warning.
5. **Small, verifiable steps.** Each milestone ends with something runnable and tested. No milestone
   is "done" on the strength of code that has never been executed.

## Environment caveat recorded at design time

The design session that produced these documents ran in a sandbox with no access to the Modular
package channels (`conda.modular.com`), the pixi installer, or the OpenStreetMap APIs. Consequences,
carried forward honestly:

- The Milestone 1 Mojo sources were written but **never compiled**. They are marked as such in
  [mojo/README.md](../mojo/README.md); `scripts/verify_env.sh` and the CI workflow exist precisely to
  close that gap on a machine with network access.
- The Python reference implementation **was executed and tested** in that session, and it is the
  oracle the Mojo port must reproduce.
- No geographic coordinates were written into the repository from memory. `data/spots/` ships a
  schema and an ingestion script, not invented latitudes. See [data/README.md](../data/README.md).
