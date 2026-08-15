# ADR 0001 — Hybrid Python/Mojo architecture, with Mojo earning its place

- **Status:** accepted
- **Date:** 2026-08-15

## Context

SailWise has two goals that can pull in opposite directions: build a genuinely useful sailing planner,
and learn Mojo deeply. The failure mode is obvious — writing everything in Mojo because it is the
project's language, ending up with a slow-to-build, hard-to-integrate application that teaches the
wrong lesson about when a systems language is the right tool.

The workload is also not uniform. Roughly:

- **I/O-bound, integration-heavy:** HTTP calls to providers, database access, caching, auth, JSON
  serialisation, the web layer. Latency here is dominated by the network.
- **CPU-bound, numeric:** wind statistics, scoring, window search, ranking, route evaluation. Uniform
  arrays of `Float64`, simple arithmetic, no I/O, embarrassingly parallel across spots.

## Decision

**Python orchestrates. Mojo computes. A workload moves to Mojo only when a benchmark says it should.**

Concretely:

1. All I/O, integration, persistence and web concerns stay in Python. Mojo performs no I/O.
2. The compute core is a set of pure functions over flat numeric arrays, with no knowledge of HTTP,
   JSON, databases or the domain's object graph.
3. Every kernel has a Python reference implementation which is the correctness oracle and the runtime
   fallback (NFR-M-02).
4. A kernel is adopted in Mojo only when `benchmarks/` shows a worthwhile margin **over NumPy** — not
   over naive Python — at a realistic input size, with the call overhead included.
5. A negative benchmark result is recorded and the Python/NumPy implementation stays. That outcome
   still teaches the intended lesson.

## Consequences

**Positive**

- The application remains shippable regardless of Mojo toolchain state — a real risk with a young
  language (R3).
- The Mojo surface stays small, which is exactly what makes SIMD and parallelism tractable to learn on.
- The forced "flat arrays at the boundary" discipline improves the Python side too: a batch-shaped
  compute API is faster and clearer even in pure Python.
- The learning is honest: the project answers *when* Mojo is the right choice, which is more valuable
  than a demonstration that it can be used everywhere.

**Negative**

- Two implementations of the same specification must be kept in sync. Mitigated by making it a
  blocking CI gate (NFR-C-01) rather than a discipline problem.
- A conversion cost at the boundary, which sets a floor on how small a payload can profitably cross
  it. This is a real constraint and it is why batching is architectural rather than an optimisation.

## Alternatives considered

- **All Mojo.** Rejected: immature web/DB ecosystem, and it would make the answer to "when is Mojo
  right?" unavailable by construction.
- **All Python + NumPy.** Genuinely viable for the current data sizes and therefore kept as the
  baseline and the fallback — but it forecloses the learning goal and the path to national-scale
  ranking.
- **Rust for the compute core.** Comparable performance, more mature tooling, but no learning goal
  and a heavier interop boundary. Reconsider only if Mojo proves unworkable in practice.
