# SailWise reference implementation

Pure-Python, standard-library-only implementation of the SailWise compute model.

It has three jobs:

1. **The specification, made executable** — [docs/05-algorithms.md](../docs/05-algorithms.md)
   is the spec; this package is what the spec means.
2. **The oracle** — the Mojo core must reproduce these numbers within 1e-9 (NFR-C-01).
3. **The runtime fallback** — the product stays shippable when the Mojo toolchain is
   unavailable (NFR-M-02).

Readability beats speed here, always. If you want it fast, that is what `mojo/` is for.

## Use

```bash
pip install -e '.[dev]'
pytest

PYTHONPATH=src python3 -m sailwise_ref.cli --profile CRUISING
PYTHONPATH=src python3 -m sailwise_ref.cli --all-profiles
```

```python
from sailwise_ref import get_profile, sailing_score
from sailwise_ref.fixtures import load_day

day = load_day()
result = sailing_score(day.hours, get_profile("CRUISING"), day.accessibility)

print(result.total)                              # 84.48…
print(result.component("wind_quality").raw)      # 0.9305…
print(result.confidence)                         # 0.90 — accessibility was UNKNOWN
```

## Modules

| Module | Contents |
|---|---|
| `constants.py` | every named constant in the model — no magic numbers elsewhere |
| `units.py` | conversions, `clamp01`, `trapezoid`, mean, stdev, slope |
| `profiles.py` | the six sailing profiles: weights and preference bands |
| `weather.py` | `HourlyWeather`, `WindStats`, trend classification |
| `score.py` | the seven components and their aggregation |
| `fixtures.py` | loading synthetic fixtures from `data/fixtures/` |
| `cli.py` | the Milestone 1 demo |

## No dependencies, on purpose

The oracle must be trivially runnable anywhere — in CI, in a benchmark harness, inside
the backend, on a machine with no wheels available. NumPy appears in `benchmarks/` as
the honest performance baseline, never here.
