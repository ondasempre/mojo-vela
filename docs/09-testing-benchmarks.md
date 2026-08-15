# 27–28. Testing Strategy and Benchmark Strategy

## 27. Testing strategy

### The shape

```
        ╱╲          e2e (few)         docker compose up → plan a day → assert the shape
       ╱  ╲         contract          adapter ↔ recorded provider payloads
      ╱────╲        integration       API + DB + cache, fixture weather provider
     ╱      ╲       property          invariants of the scoring model
    ╱────────╲      unit (many)       pure functions, both languages
   ╱  golden  ╱     cross-language    Mojo ≡ Python within 1e-9   ← the gate that matters
  ╱──────────╱
```

### Unit tests

Python with `pytest`, Mojo with `mojo test`. Both implement the same specification
([05-algorithms.md](05-algorithms.md)) and therefore share the same test *cases*, expressed once in
`data/fixtures/` and consumed by both.

Required coverage of the scoring and ranking paths: ≥ 90 % (NFR-C-02).

### Golden / cross-language tests (NFR-C-01)

The Python reference implementation is the oracle. `scripts/gen_golden.py` runs it over the fixture
set and emits:

1. `data/fixtures/golden_scores_v1.json` — for the Python and integration suites;
2. a Mojo source fragment of the same constants — for `mojo test`, because Mojo has no JSON parser in
   its standard library and adding one just to read test data would be the tail wagging the dog.

CI fails if the two implementations diverge by more than `1e-9` on any component. This single gate is
what makes the whole "optimise in Mojo" programme safe: every SIMD or parallel variant must reproduce
the scalar result exactly, or it does not merge.

### Property-based tests (`hypothesis`)

Invariants worth asserting over generated inputs, because they catch the bugs examples miss:

| Property | Statement |
|---|---|
| Range | `0 ≤ score ≤ 100` for any physically-possible input |
| Determinism | same input → identical output, run twice |
| Weight normalisation | scaling all weights by *k* leaves the score unchanged |
| Monotonicity in band | inside `[lo_ideal, hi_ideal]`, raising wind never lowers `wind_quality` |
| Stability | adding variance while holding the mean never raises `wind_stability` |
| Safety independence | changing weights never removes a warning |
| Window validity | the best window is contiguous, ≥ `D_min`, and contains no excluded hour |
| Ranking sanity | a dominating spot (≥ on every component) never ranks lower |

### Contract tests

Each provider adapter is tested against **recorded** payloads (`data/contracts/{provider}/*.json`),
never against the live service — deterministic, offline, and free of quota. A schema check runs
separately against the live API on a schedule, so an upstream change surfaces as a failing scheduled
job rather than as a production incident.

### Integration and e2e

Integration: FastAPI `TestClient` + Postgres/Redis in containers + `FixtureWeatherProvider`.
E2E: `docker compose up`, request a plan, assert the response shape, provenance envelope and
disclaimer are present.

### Safety-specific tests

A dedicated suite, because these are the assertions that must never regress:

- a CRITICAL warning is present in the output regardless of the weight set;
- `is_recommended` is false whenever a CRITICAL warning exists, at any score;
- the disclaimer is present in every plan response;
- no code path can render a route or plan without its confidence label.

### What is *not* tested

Forecast accuracy — that is the provider's business, not SailWise's. What *is* tested is that SailWise
transports, labels and combines the provider's numbers faithfully. Separately, the forecast-vs-observed
data in the sailing log makes provider quality measurable over time; that is analytics, not a test.

### CI pipeline

```
lint (ruff, mypy --strict on domain/services)
  → python unit + property tests
  → mojo build + mojo test
  → golden cross-language comparison        ← blocking
  → integration (compose services)
  → security: secret scan, dependency audit
  → benchmarks (informational on PRs; regression-gated on main)
```

A Mojo toolchain failure must not block a Python-only change: the Mojo job is required only when
`mojo/**` changes, and the runtime always retains the Python fallback (NFR-M-02).

## 28. Benchmark strategy

### The honesty rules

The brief is explicit and it is right: **measured or not published**. Concretely:

1. No number appears in the README, the docs or a talk unless it was produced by
   `benchmarks/run.py` on a named machine, and the run is reproducible.
2. Every published figure carries: machine (CPU model, core count), OS, Mojo version, Python version,
   input size, iteration count, and the variance (median + p95 + min, not a lone "best of").
3. The baseline is **honest**: idiomatic Python *and* NumPy. Comparing optimised Mojo against a
   deliberately naive Python loop is marketing, not engineering — and it would teach the wrong lesson,
   which matters more here because the point of this project is to learn.
4. Correctness is checked inside the benchmark harness. A fast wrong answer scores zero.
5. Warm-up iterations are discarded; the timer measures compute only, never I/O.

### What gets measured

| Workload | Why it is interesting |
|---|---|
| Wind statistics over 24 h × N spots | Trivially vectorisable reduction — the SIMD baseline |
| Sailing score, N spots | Branchy but uniform; tests whether branches spoil vectorisation |
| Best-window search | Sliding reduction; the interesting one |
| Full ranking + top-k, N ∈ {10, 100, 1k, 10k, 100k} | The scaling curve; where parallelism should appear |
| Route evaluation, N routes × M legs | Nested, less regular |

### Variants compared

```
python-loop     idiomatic pure Python
python-numpy    vectorised NumPy            ← the baseline that must be beaten to claim anything
mojo-scalar     direct port, no tricks
mojo-optimised  layout + hoisting + fewer passes
mojo-simd       explicit SIMD
mojo-parallel   parallelize() over spots
```

### Metrics

Execution time (median, p95), throughput (spots/s), allocations, peak RSS, and speed-up versus each
baseline. Scaling is reported as a curve, not a single number — a 4× speed-up at N = 10 and at
N = 100,000 are different claims about different bottlenecks.

### Report format

`benchmarks/results/{date}-{machine}.json` (machine-readable) plus a generated Markdown table. The
README links to the latest run and states the machine. Example of the *format* — the values are
placeholders until a real run fills them in:

```
ALGORITHM: Sailing Spot Ranking       N = 10,000 spots × 24 h
machine: <cpu>, <cores> cores | mojo <version> | python <version> | 2026-xx-xx

variant           median      p95     speed-up vs numpy
python-loop        — ms       — ms          —
python-numpy       — ms       — ms        1.00×
mojo-scalar        — ms       — ms          —
mojo-simd          — ms       — ms          —
mojo-parallel      — ms       — ms          —
```

Dashes stay dashes until the benchmark runs. That rule is the entire point.

### Regression gating

On `main`, a > 20 % regression against the stored baseline for the same machine class fails the
build. On pull requests, benchmarks are informational — CI runners are too noisy to gate on, and a
flaky performance gate teaches people to ignore CI.

### The decision the benchmarks exist to inform

Per [adr/0001](adr/0001-hybrid-python-mojo.md), a workload moves to Mojo only when the benchmark shows
a worthwhile margin **over NumPy** at a realistic N, and the margin survives the call overhead. If
NumPy wins, NumPy stays. Recording a case where Mojo did not win is a successful outcome of this
strategy, not an embarrassment.
