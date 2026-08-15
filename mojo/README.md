# SailWise compute core (Mojo)

Pure numerics: scoring, and later ranking, window search and route evaluation.
**No I/O, no JSON, no networking** — that constraint is what keeps this code
vectorisable and testable ([ADR 0001](../docs/adr/0001-hybrid-python-mojo.md)).

## Status: written, not yet compiled

These sources were authored in an environment without access to the Modular package
channels, so **they have never been through the compiler.** Treat the first
`pixi run test` as part of Milestone 1: expect to fix compile errors, and expect the
tests to be right about the numbers once it builds — the golden values come from the
Python reference, which *was* executed.

If a construct here does not compile against your Mojo version, fix the code, not the
golden values.

## Commands

```bash
pixi install        # install the pinned toolchain
pixi run test       # all three test files
pixi run demo       # score the synthetic Dervio day for all six profiles
pixi run build      # build a standalone binary into build/
pixi run fmt        # format
```

Without pixi:

```bash
mojo run -I src main.mojo
mojo run -I src tests/test_units.mojo
mojo run -I src tests/test_wind.mojo
mojo run -I src -I tests tests/test_score.mojo
```

Tests use the standard library's `TestSuite` with `discover_tests`, so each test file
is an ordinary program with a `main()` — run the file to run its tests.

## Layout

| File | Contents |
|---|---|
| `src/sailwise/units.mojo` | `clamp01`, `trapezoid`, `mean`, `stdev_population`, slope, unit conversions |
| `src/sailwise/weather.mojo` | `HourlyWeather`, `WindStats`, `compute_wind_stats`, trend classification |
| `src/sailwise/score.mojo` | `Band`, `Weights`, `SailingProfile`, `Accessibility`, `sailing_score` |
| `src/sailwise/profiles.mojo` | the six default profiles |
| `src/sailwise/fixture.mojo` | the synthetic Dervio day as literals |
| `tests/golden_values.mojo` | **generated** by `scripts/gen_golden.py` — do not edit |

## The contract with Python

`python/src/sailwise_ref/` implements the same specification and is the oracle. The
two must agree within 1e-9 on the golden fixtures; `tests/test_score.mojo` enforces it.

That gate is what makes optimisation safe later: SIMD and parallel variants must
reproduce the scalar result exactly, or they do not merge.

Changing the model? Follow the six-step workflow in
[CONTRIBUTING.md](../CONTRIBUTING.md#changing-the-scoring-model). Never regenerate the
golden files to make a test pass.
