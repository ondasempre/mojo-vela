# SailWise — Intelligent Sailing Planner

> Where should I sail today, when should I leave, and what will it be like?

SailWise turns forecast data into a sailing decision: a ranked answer with a
0–100 Sailing Score, a recommended time window, safety warnings, and an explanation of
every number behind it. Python orchestrates; a Mojo core does the computing.

Initial focus: **Lake Como, from Dervio.** Designed from the start to extend to every
Italian lake, then the Mediterranean, then anywhere — nothing in the data model
hardcodes a body of water.

## What SailWise is not

- **Not a navigation instrument.** No depth data, no obstructions, no traffic rules.
- **Not a safety clearance.** The score is decision support. Warnings are produced by
  a separate pipeline that a high score can never override.
- **Not a replacement** for official forecasts, port authority notices, or the
  judgement of whoever is responsible for the boat.

> Always verify official weather, navigation and local safety information before
> departure.

## Status

**Milestones 1–4 of 10.** The app runs locally: real forecasts, ranked spots, safety
warnings and a web UI. See [docs/10-roadmap.md](docs/10-roadmap.md).

| Component | State |
|---|---|
| Architecture & specification | complete — [docs/](docs/ARCHITECTURE.md) |
| Scoring, best window, safety gates, ranking | working, tested (115 tests) |
| API + web UI, Open-Meteo adapter, cache | working, tested (65 tests) |
| Parking (car + moto), food, picnic, clubs from OpenStreetMap | working |
| Webcams, events and photographs | containers ready, datasets ship empty on purpose |
| Mojo compute core | written; **not yet compiled** — see the caveat below |
| Database, accounts, sailing log, AI | designed, not built (M6+) |

> **Honest caveat.** The environment that produced this repository had no access to
> the Modular package channels, so the Mojo sources have never been compiled. The
> Python side was executed and tested. Run `./scripts/verify_env.sh` on a machine with
> network access to close that gap — and expect to fix compile errors in the Mojo
> files on the first run. The golden tests exist precisely so that "it compiles" and
> "it is correct" are checked separately.

## Quickstart

```bash
./scripts/run_local.sh            # → http://127.0.0.1:8000
./scripts/run_local.sh --demo     # synthetic data, fully offline
```

On Windows PowerShell (which cannot run `.sh` files):

```powershell
.\scripts\run_local.ps1
.\scripts\run_local.ps1 -Demo
```

That starts the API and the web UI in one process. No API key needed: the default
weather provider's free tier requires none. Full guide:
[docs/running-locally.md](docs/running-locally.md).

The spot dataset ships without coordinates on purpose, so the first run resolves them
in the background (one request per second, priority order, cached to disk afterwards).
Dervio and Colico are available within seconds; all 33 spots inside a minute.

Other entry points:

```bash
# the engine on its own, no server
cd python && pip install -e '.[dev]' && pytest
PYTHONPATH=src python3 -m sailwise_ref.cli --all-profiles

# the Mojo compute core
curl -fsSL https://pixi.sh/install.sh | sh
cd mojo && pixi install && pixi run test && pixi run demo

# everything at once
./scripts/verify_env.sh
```

Sample output of the reference scorer on the synthetic Dervio day:

```
--- CRUISING --------------------------------------------------
wind  mean  10.2 kn | max  15.0 | gust max  17.8 | sd  3.3 | gust factor 1.26
      consistency 0.46 | trend RISING_THEN_EASING

  wind_quality        31.02 /  33.33   raw 0.931  weight 0.30
  wind_stability      12.13 /  22.22   raw 0.546  weight 0.20
  weather             19.44 /  22.22   raw 0.875  weight 0.20
  rain                 5.22 /   5.56   raw 0.940  weight 0.05
  temperature         11.11 /  11.11   raw 1.000  weight 0.10
  water_conditions     5.56 /   5.56   raw 1.000  weight 0.05
  accessibility                 UNKNOWN   (weight 0.10, excluded)
  TOTAL               84.48 / 100.00   confidence 0.90
```

Note `accessibility … UNKNOWN`. That is the design working: no facility data has been
sourced yet, so the component is excluded and the confidence drops, rather than being
filled with a plausible guess.

## The rules this project is built on

1. **Python orchestrates, Mojo computes** — and a workload only moves to Mojo when a
   benchmark beats NumPy, not because Mojo is the project's language.
   ([ADR 0001](docs/adr/0001-hybrid-python-mojo.md))
2. **No provider lock-in.** Every external source sits behind a port.
   ([ADR 0002](docs/adr/0002-weather-provider-abstraction.md))
3. **Every number carries its provenance** — `FORECAST`, `ESTIMATED`, `CACHED`,
   `USER`, `UNKNOWN`. `UNKNOWN` is a first-class answer; inventing a value is a defect.
4. **The score is advice, never a safety clearance.**
5. **Measured or not published.** Benchmark numbers come from a named machine and a
   reproducible run, or they do not appear.

## Documentation

| | |
|---|---|
| [Architecture index](docs/ARCHITECTURE.md) | start here — maps all 35 design deliverables |
| [Product vision, personas, user stories](docs/01-product-vision.md) | |
| [Requirements](docs/02-requirements.md) | FR/NFR, referenced from tests |
| [System architecture](docs/03-system-architecture.md) | components, data flow, API, Docker |
| [Data model](docs/04-data-model.md) | entities, schema, provenance |
| [**Algorithms**](docs/05-algorithms.md) | Sailing Score, ranking, routing, personalisation |
| [Integrations](docs/06-integrations.md) | weather providers, Windy strategy, cache, geospatial |
| [AI layer](docs/07-ai-layer.md) | |
| [Security & privacy](docs/08-security-privacy.md) | |
| [Testing & benchmarks](docs/09-testing-benchmarks.md) | |
| [Roadmap](docs/10-roadmap.md) | milestones, MVPs, risks, technical debt |
| [**Milestone 1**](docs/milestone-1.md) | setup, exit criteria, exercises |
| [Percorso Mojo (IT)](docs/mojo-learning-path.it.md) | the ten learning levels, in Italian |

## Data sources and attribution

- Weather: **Open-Meteo** (CC BY 4.0, non-commercial tier) is the default provider.
  A **Windy** adapter exists behind an API key and an explicit terms acknowledgement —
  see [ADR 0002](docs/adr/0002-weather-provider-abstraction.md).
- Geodata: **OpenStreetMap** (ODbL) — "© OpenStreetMap contributors".
- Datasets under `data/` carry their own licensing; see [data/README.md](data/README.md).

## Licence

MIT for the code. `data/` is licensed separately — OSM-derived content is ODbL.
