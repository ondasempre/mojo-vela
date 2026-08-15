#!/usr/bin/env python3
"""Assert that the Mojo fixture and the JSON fixture contain the same numbers.

The compute core has no JSON parser on purpose (ADR 0001), so the synthetic Dervio
day exists twice: once as ``data/fixtures/day_dervio_synthetic.json`` and once as
Mojo literals in ``mojo/src/sailwise/fixture.mojo``. Duplication is acceptable here
only because this script makes drift impossible to miss — without it, the golden
test could pass while the two implementations scored different days, which is
exactly the kind of bug that produces plausible wrong numbers.

    python3 scripts/check_fixture_sync.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "data" / "fixtures" / "day_dervio_synthetic.json"
MOJO_PATH = ROOT / "mojo" / "src" / "sailwise" / "fixture.mojo"

FIELDS = (
    "hour",
    "wind_kn",
    "gust_kn",
    "wind_dir_deg",
    "temp_c",
    "precip_mm",
    "precip_prob",
    "cloud_frac",
    "visibility_m",
    "storm_prob",
)

CALL_RE = re.compile(r"HourlyWeather\(([^)]*)\)")


def parse_mojo_rows(text: str) -> list[list[float]]:
    rows = []
    for match in CALL_RE.finditer(text):
        args = [a.strip() for a in match.group(1).split(",")]
        if len(args) != len(FIELDS):
            continue
        try:
            rows.append([float(a) for a in args])
        except ValueError:
            continue  # a constructor call that is not a literal row
    return rows


def main() -> int:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    json_rows = [[float(hour[f]) for f in FIELDS] for hour in payload["hours"]]
    mojo_rows = parse_mojo_rows(MOJO_PATH.read_text(encoding="utf-8"))

    if len(json_rows) != len(mojo_rows):
        print(
            f"row count differs: JSON has {len(json_rows)}, Mojo has {len(mojo_rows)}",
            file=sys.stderr,
        )
        return 1

    problems = []
    for index, (a, b) in enumerate(zip(json_rows, mojo_rows)):
        for field, x, y in zip(FIELDS, a, b):
            if abs(x - y) > 1e-12:
                problems.append(f"  hour index {index}, field {field}: JSON {x} != Mojo {y}")

    if problems:
        print("Fixture drift detected between:", file=sys.stderr)
        print(f"  {JSON_PATH.relative_to(ROOT)}", file=sys.stderr)
        print(f"  {MOJO_PATH.relative_to(ROOT)}", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        return 1

    print(f"Fixtures agree: {len(json_rows)} hours, {len(FIELDS)} fields each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
