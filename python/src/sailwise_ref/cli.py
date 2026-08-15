"""Milestone 1 demo: score a synthetic day and print the breakdown.

    python -m sailwise_ref.cli --profile CRUISING

The output is deliberately shaped like the Mojo demo's output so that the two can be
compared side by side while you learn.
"""

from __future__ import annotations

import argparse

from .fixtures import load_day
from .profiles import PROFILES, ProfileId, get_profile
from .score import sailing_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SailWise reference scorer (Milestone 1)")
    parser.add_argument("--profile", default="CRUISING", choices=[p.value for p in ProfileId])
    parser.add_argument("--fixture", default="day_dervio_synthetic")
    parser.add_argument("--all-profiles", action="store_true", help="score every profile")
    args = parser.parse_args(argv)

    day = load_day(args.fixture)
    profiles = list(PROFILES.values()) if args.all_profiles else [get_profile(args.profile)]

    print("=" * 62)
    print("SAILWISE — Sailing Score (Milestone 1, reference implementation)")
    print("=" * 62)
    print(f"Spot     : {day.spot_name} ({day.spot_id})")
    print(f"Date     : {day.date}")
    print(f"Hours    : {day.hours[0].hour:02d}:00 – {day.hours[-1].hour:02d}:00")
    print("Data     : SYNTHETIC FIXTURE — not a forecast, not a real day")
    print()

    for profile in profiles:
        result = sailing_score(day.hours, profile, day.accessibility)
        print(f"--- {profile.id.value} " + "-" * (58 - len(profile.id.value)))
        w = result.wind
        print(
            f"wind  mean {w.mean_kn:5.1f} kn | max {w.max_kn:5.1f} | gust max {w.gust_max_kn:5.1f}"
            f" | sd {w.stdev_kn:4.1f} | gust factor {w.gust_factor:4.2f}"
        )
        print(f"      consistency {w.consistency:.2f} | trend {w.trend}")
        print()
        for c in result.components:
            if c.raw is None:
                print(f"  {c.id:<18} {'UNKNOWN':>18}   (weight {c.weight:.2f}, excluded)")
            else:
                print(
                    f"  {c.id:<18} {c.points:6.2f} / {c.max_points:6.2f}"
                    f"   raw {c.raw:.3f}  weight {c.weight:.2f}"
                )
        print(f"  {'TOTAL':<18} {result.total:6.2f} / 100.00   confidence {result.confidence:.2f}")
        print()

    print("Notes:")
    for note in result.notes:
        print(f"  - {note}")
    print()
    print("SailWise is decision support, not a safety clearance.")
    print("Always check official forecasts and notices before departure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
