# ADR 0003 — Staging the Python↔Mojo boundary: CLI first, in-process later

- **Status:** accepted
- **Date:** 2026-08-15

## Context

Python must call the Mojo compute kernels. Three mechanisms exist, with very different maturity and
cost profiles:

1. **Subprocess / CLI.** Mojo builds a binary; Python invokes it and exchanges a compact numeric
   payload over stdin/stdout. Cost: process spawn (~ms) plus serialisation.
2. **Shared library via FFI.** `mojo build --emit shared-lib`, called through `ctypes`/`cffi` with a
   C ABI. Cost: a hand-written boundary; benefit: no process spawn.
3. **Mojo as a Python extension module.** Mojo has built-in support for defining Python extension
   modules, and Python can import a `.mojo` module through Modular's import hook, which compiles it to
   a shared library behind the scenes. This is the most ergonomic option — and, as of 2026, Modular
   still describes it as early and actively developing, with limitations such as restrictions on
   argument counts and keyword arguments.

The compute payload is small and batch-shaped: for 1,000 spots × 24 hours × 9 fields, roughly 1.7 MB
of `Float64`, computed once per request.

## Decision

**Stage the boundary. Start with the CLI, adopt in-process only when measurement justifies it.**

- **M1–M3: CLI.** A `sailwise-compute` binary reads a length-prefixed binary array of `Float64` from
  stdin and writes results to stdout. The contract is a documented byte layout with a version header.
- **M4–M9: keep the CLI**, but move the process behind a small worker pool so the spawn cost is paid
  once rather than per request, if measurement shows it matters.
- **M10: evaluate the in-process extension module**, and adopt it if benchmarks show the boundary is a
  material fraction of request latency and the interop limitations do not bite.
- **In all cases the `ComputeEngine` facade hides the mechanism.** Swapping it is one class.
- **The Python backend remains selectable at runtime** (`COMPUTE_BACKEND=python|mojo`).

## Rationale

- The batch is computed **once per request**, not per spot. A ~1–5 ms process cost against a
  request budget of 300 ms, in a workload dominated by provider I/O, is not where the latency is.
  Optimising it first would be optimising the wrong thing.
- A process boundary is the most robust possible insulation from a young language's churn: a Mojo
  breaking change can break the *binary's build*, and the backend keeps running on the Python fallback.
- Debugging is trivial — the CLI can be run by hand with a fixture file, which also makes the kernel
  independently benchmarkable without Python in the picture.
- Deferring the interop path costs nothing architecturally, and by M10 it will have matured further.

## Consequences

**Positive:** simple, debuggable, version-proof; kernels stay pure; the compute core is testable and
benchmarkable standalone.

**Negative:** serialisation and spawn overhead that the in-process path would avoid; a byte-layout
contract to version and test (mitigated by a version header and a round-trip test on both sides).

## Wire format v1

```
header : magic "SWC1" (4 bytes) | version u16 | kernel_id u16 | n_spots u32 | n_hours u32 | n_fields u32
body   : float64[n_spots * n_hours * n_fields]   struct-of-arrays, field-major
params : float64[n_params]                        weights, bands, thresholds
output : float64[n_spots * n_outputs]
```

Little-endian throughout. Field order is defined once in `data/schemas/compute_layout_v1.json` and
asserted by tests on both sides — a mismatch here would produce plausible wrong numbers, which is the
worst kind of bug, so it gets its own test rather than a comment.
