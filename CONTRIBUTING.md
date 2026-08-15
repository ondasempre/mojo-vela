# Contributing to SailWise

## The five rules

Everything below follows from these. If a change conflicts with one of them, the rule
wins, or the rule gets changed first in an ADR.

1. **Python orchestrates, Mojo computes.** A workload moves to Mojo when a benchmark
   beats NumPy — not because Mojo is the project's language.
2. **No provider lock-in.** External sources go behind a port in `ports/`.
3. **Every number carries its provenance.** `UNKNOWN` is a valid answer. Inventing a
   plausible value is a defect, not a convenience.
4. **The score is advice, never a safety clearance.** Safety warnings live in their
   own pipeline and cannot be suppressed by scoring changes.
5. **Measured or not published.** No performance number without the machine, the
   versions and a reproducible run.

## Data contributions

The most valuable and most approachable contribution is **spot data** — launch points,
parking, clubs, services around a lake or a stretch of coast. No Mojo required.

Rules, from [data/README.md](data/README.md):

- every value needs a **source** and a **retrieval date**;
- unknown stays `null`; never fill a gap from memory or from an LLM;
- coordinates for a launch point should be verified by a human who has been there, or
  marked `ingested_unverified`;
- OSM-derived data is ODbL — attribution and share-alike apply.

## Changing the scoring model

The scoring model has a specific workflow because two implementations must agree:

1. Change **[docs/05-algorithms.md](docs/05-algorithms.md) first.** The document is
   the specification; the code follows it.
2. Change the **Python reference** (`python/src/sailwise_ref/`) and its tests.
3. Run `python3 scripts/gen_golden.py` to regenerate the golden values.
4. Change the **Mojo implementation** to match.
5. Run `./scripts/verify_env.sh`. The golden test must pass within 1e-9.
6. Bump `SCORE_MODEL_VERSION` in **both** implementations if behaviour changed.

Never regenerate the golden files to make a failing test pass. A golden diff is either
a deliberate model change (steps 1 and 6 above) or a bug you have just found.

## Code standards

- **Named constants only.** A bare number in scoring or ranking code is a review
  blocker. Constants live in `constants.py` / the `alias` block at the top of the
  corresponding Mojo module.
- **No I/O in the compute core.** No HTTP, no files, no JSON in `mojo/src/` or in
  `compute/`.
- **No business logic in adapters.** Adapters normalise and convert units; that is all.
- `TODO` requires an issue number. `FIXME` fails lint.
- Python: `ruff` + `mypy --strict` on `domain/` and `services/`. Mojo: `mojo format`.
- Conventional commits (`feat:`, `fix:`, `docs:`, `perf:`, `test:`, `chore:`).

## Tests

| Change | Required tests |
|---|---|
| Scoring / ranking | unit + property + golden in both languages |
| Adapter | contract test against a recorded payload — never against the live API |
| Safety gates | a test proving the warning survives any weight configuration |
| Performance | a benchmark run before and after, with the machine recorded |

## Architecture decisions

Anything that changes a boundary, a dependency direction or a provider relationship
needs an ADR in `docs/adr/`. Copy the format of the existing three: context, decision,
consequences (positive *and* negative), alternatives considered.

## What gets rejected

- Data without provenance.
- Performance claims without a reproducible measurement.
- Anything that makes the score look like a safety guarantee.
- Scraping a service whose terms forbid it, or treating a web page as an API.
- Mojo code without a Python reference to check it against.
