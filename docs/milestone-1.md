# Milestone 1 — Environment, first structs, score v0

**Goal:** get a working Mojo toolchain, write the first real Mojo code, and prove it
computes exactly the same numbers as a Python reference implementation.

**Deliberately not in scope:** HTTP, databases, real forecasts, multiple spots, the
best-window search, safety gates, SIMD. Every one of those has its own milestone. The
value of M1 is a verified foundation, not coverage.

**Estimated effort:** one evening for the environment, one or two for the code.

## Exit criteria

| # | Criterion | How to check |
|---|---|---|
| 1 | Mojo toolchain installed and pinned | `cd mojo && pixi run demo` |
| 2 | Python reference tests pass | `cd python && pytest` |
| 3 | Mojo tests pass | `cd mojo && pixi run test` |
| 4 | Both implementations agree within 1e-9 | the golden tests in `mojo/tests/test_score.mojo` |
| 5 | One command verifies all of it | `./scripts/verify_env.sh` |

## Setup

```bash
# 1. Install pixi (Modular's recommended way to install Mojo)
curl -fsSL https://pixi.sh/install.sh | sh
exec $SHELL          # reload PATH

# 2. Install the pinned Mojo toolchain for this project
cd mojo
pixi install
pixi run demo        # should print six profile breakdowns for the synthetic Dervio day

# 3. The Python side (no third-party dependencies except pytest)
cd ../python
pip install -e '.[dev]'
pytest

# 4. Everything at once
cd ..
./scripts/verify_env.sh
```

If `pixi install` cannot reach `conda.modular.com`, you are behind a proxy or offline.
The Python half of the project works without Mojo, and `verify_env.sh` will say so
rather than failing.

## What exists after M1

```
mojo/
  pixi.toml                    pinned toolchain + task shortcuts
  main.mojo                    demo: score the synthetic day for all six profiles
  src/sailwise/
    units.mojo                 clamp01, trapezoid, mean, stdev, slope, conversions
    weather.mojo               HourlyWeather, WindStats, compute_wind_stats
    score.mojo                 Band, Weights, SailingProfile, Accessibility, sailing_score
    profiles.mojo              the six default profiles
    fixture.mojo               the synthetic Dervio day as Mojo literals
  tests/
    test_units.mojo            primitives
    test_wind.mojo             statistics, including the divide-by-zero guard
    test_score.mojo            contract properties + the golden cross-language test
    golden_values.mojo         GENERATED — do not edit

python/
  src/sailwise_ref/            the same model, in Python: the oracle and the fallback
  tests/                       79 tests

scripts/
  gen_golden.py                regenerates golden_values.mojo from the Python oracle
  check_fixture_sync.py        asserts the JSON and Mojo fixtures hold the same numbers
  verify_env.sh                one command to check the whole environment
```

## The workflow this milestone establishes

This is the loop every later milestone follows, and it is the reason the project can
optimise aggressively later without fear:

```
  1. Write the specification in docs/05-algorithms.md
             ↓
  2. Implement it in Python (readable, obviously correct, tested)
             ↓
  3. python3 scripts/gen_golden.py    →  golden_values.mojo
             ↓
  4. Implement it in Mojo
             ↓
  5. mojo run tests/test_score.mojo   →  must agree within 1e-9
             ↓
  6. Only now: optimise the Mojo version (SIMD, parallel, layout).
     Step 5 re-runs on every change and tells you the moment you break it.
```

Steps 2 and 3 are what make step 6 safe. Without an oracle, "I made it faster" and
"I made it wrong" are indistinguishable — and a scoring engine that is subtly wrong is
worse than a slow one.

## Exercises

Do these in order; each one adds a real capability the roadmap needs.

**1. Beaufort scale.** Add `fn beaufort(wind_kn: Float64) -> Int` to `units.mojo` with
its test. Boundaries are the interesting part — Force 4 is 11–16 kn, so what is 16.0?
Write the test first and decide deliberately.

**2. Mean wind direction.** Add `fn mean_direction(dirs: List[Float64]) -> Float64`.
The naive average of 350° and 10° is 180°, which is exactly backwards. The fix is to
average the unit vectors (`atan2(mean(sin), mean(cos))`). Test it with the wrap-around
case, because that is the only case that matters.

**3. Break the golden test on purpose.** Change `CV_MAX` in `score.mojo` from 0.60 to
0.55 and run the tests. Read the failure. Now change it in the Python constants too,
regenerate, and watch it pass again. This is the mechanism that will protect you for
the rest of the project — meet it while the stakes are zero.

**4. Add a profile.** `FOILING`: high wind band, very low chop sensitivity, stability
weighted heavily. Add it in both languages, extend the golden generator, verify.

**5. Measure something.** Time `sailing_score` over 100,000 synthetic days in both
languages. Write the numbers, the machine and the versions into
`benchmarks/results/`. Do not round them in your favour, and do not publish them
anywhere without the machine description (docs/09-testing-benchmarks.md).

## What Milestone 2 adds

Best sailing window (the first sliding-window algorithm, and the first honest SIMD
candidate), the safety-gate pipeline, and the warning catalogue. The window search is
where the Mojo work starts to be genuinely worth doing rather than merely instructive.
