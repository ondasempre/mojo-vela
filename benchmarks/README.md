# Benchmarks

Strategy and rules: [docs/09-testing-benchmarks.md](../docs/09-testing-benchmarks.md).

## The rule

**Measured or not published.** No number appears in the README, the docs, an issue or
a talk unless it came from a reproducible run on a named machine. There are currently
**no results in this directory**, because nothing has been measured yet — the Mojo
core has not even been compiled. Dashes stay dashes.

## Baselines

The comparison is against **NumPy**, not against a naive Python loop. Beating an
interpreted loop with compiled SIMD code proves nothing anyone doubted, and publishing
it would be marketing rather than engineering — which matters more here than usual,
because the point of this project is to learn *when* Mojo is the right choice.

```
python-loop      idiomatic pure Python
python-numpy     vectorised NumPy          ← the baseline that must be beaten
mojo-scalar      direct port
mojo-optimised   layout and pass reduction
mojo-simd        explicit SIMD
mojo-parallel    parallelize() over spots
```

## Required metadata for every result

CPU model, core count, OS, Mojo version, Python version, NumPy version, input size,
iteration count, warm-up count, median, p95, min. A single "best of" number is not a
result.

## Correctness first

The harness verifies every variant against the Python oracle before timing it. A fast
wrong answer scores zero, and the golden tolerance is the same 1e-9 used in CI.

## Output

`results/{date}-{machine}.json`, plus a generated Markdown table. Results that are
specific to a local machine and not curated go in `*.local.json`, which is gitignored.

## The question every benchmark exists to answer

Not "is Mojo faster?" but: **does this speed-up change what the product can do?**
Ranking 50 spots faster inside a request dominated by 280 ms of provider I/O changes
nothing. Ranking 10,000 spots within budget is a feature that did not exist before.
Record the answer either way — a documented "no" is a successful result
([ADR 0001](../docs/adr/0001-hybrid-python-mojo.md)).
