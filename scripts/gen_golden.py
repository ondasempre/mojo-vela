#!/usr/bin/env python3
"""Generate the golden outputs that pin the Mojo implementation to the Python oracle.

Writes two things from one source of truth:

1. ``data/fixtures/golden_scores_v1.json`` — machine-readable, used by the Python
   and integration suites.
2. ``mojo/tests/golden_values.mojo`` — the same constants as Mojo aliases, because
   Mojo has no JSON parser in its standard library and writing one just to read test
   data would be the tail wagging the dog.

Run it whenever the scoring model changes on purpose, and never to make a failing
test pass. A diff in this file is a deliberate change to the model, and it must come
with a bump of SCORE_MODEL_VERSION and an update to docs/05-algorithms.md.

    python3 scripts/gen_golden.py [--check]

``--check`` regenerates into memory and fails if the committed files differ, which is
what CI runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from sailwise_ref.constants import SCORE_MODEL_VERSION
from sailwise_ref.fixtures import load_day
from sailwise_ref.profiles import PROFILES, ProfileId
from sailwise_ref.score import sailing_score

FIXTURE = "day_dervio_synthetic"
JSON_PATH = ROOT / "data" / "fixtures" / "golden_scores_v1.json"
MOJO_PATH = ROOT / "mojo" / "tests" / "golden_values.mojo"


def build() -> tuple[dict, str]:
    day = load_day(FIXTURE)
    payload: dict = {
        "generated_by": "scripts/gen_golden.py",
        "model_version": SCORE_MODEL_VERSION,
        "fixture": FIXTURE,
        "warning": "Generated file. Do not edit by hand. Regenerate with scripts/gen_golden.py.",
        "wind": {},
        "profiles": {},
    }

    stats_profile = PROFILES[ProfileId.CRUISING]
    reference = sailing_score(day.hours, stats_profile, day.accessibility)
    w = reference.wind
    payload["wind"] = {
        "mean_kn": w.mean_kn,
        "max_kn": w.max_kn,
        "min_kn": w.min_kn,
        "gust_max_kn": w.gust_max_kn,
        "gust_mean_kn": w.gust_mean_kn,
        "stdev_kn": w.stdev_kn,
        "cv": w.cv,
        "gust_factor": w.gust_factor,
        "consistency": w.consistency,
        "slope_kn_per_h": w.slope_kn_per_h,
        "trend": w.trend,
    }

    for profile_id, profile in PROFILES.items():
        result = sailing_score(day.hours, profile, day.accessibility)
        payload["profiles"][profile_id.value] = {
            "total": result.total,
            "confidence": result.confidence,
            "components": {
                c.id: {"raw": c.raw, "points": c.points, "max_points": c.max_points}
                for c in result.components
            },
        }

    return payload, render_mojo(payload)


def render_mojo(payload: dict) -> str:
    lines = [
        '"""Golden values for the cross-language equivalence tests (NFR-C-01).',
        "",
        "GENERATED FILE — do not edit by hand.",
        "Regenerate with:  python3 scripts/gen_golden.py",
        "",
        "Source of truth: the Python reference implementation in python/src/sailwise_ref.",
        f'Model version: {payload["model_version"]}',
        '"""',
        "",
        "# Wind statistics over the synthetic Dervio day.",
    ]

    for key, value in payload["wind"].items():
        if isinstance(value, str):
            continue
        lines.append(f"alias GOLDEN_WIND_{key.upper()}: Float64 = {value!r}")

    lines.append("")
    lines.append("# Total score per profile.")
    for profile_id, data in payload["profiles"].items():
        lines.append(f"alias GOLDEN_TOTAL_{profile_id}: Float64 = {data['total']!r}")

    lines.append("")
    lines.append("# Component raw sub-scores for CRUISING (the reference profile).")
    for cid, comp in payload["profiles"]["CRUISING"]["components"].items():
        raw = comp["raw"]
        if raw is None:
            lines.append(f"# {cid}: UNKNOWN (excluded from aggregation)")
        else:
            lines.append(f"alias GOLDEN_CRUISING_{cid.upper()}: Float64 = {raw!r}")

    lines.append("")
    lines.append("#: Maximum permitted absolute difference between the two implementations.")
    lines.append("alias GOLDEN_TOLERANCE: Float64 = 1e-9")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed files are stale")
    args = parser.parse_args()

    payload, mojo_src = build()
    json_src = json.dumps(payload, indent=2, sort_keys=False) + "\n"

    if args.check:
        stale = []
        if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != json_src:
            stale.append(str(JSON_PATH.relative_to(ROOT)))
        if not MOJO_PATH.exists() or MOJO_PATH.read_text(encoding="utf-8") != mojo_src:
            stale.append(str(MOJO_PATH.relative_to(ROOT)))
        if stale:
            print("Golden files are stale:", ", ".join(stale), file=sys.stderr)
            print("Run: python3 scripts/gen_golden.py", file=sys.stderr)
            return 1
        print("Golden files are up to date.")
        return 0

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    MOJO_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json_src, encoding="utf-8")
    MOJO_PATH.write_text(mojo_src, encoding="utf-8")
    print(f"wrote {JSON_PATH.relative_to(ROOT)}")
    print(f"wrote {MOJO_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
