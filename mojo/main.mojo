"""Milestone 1 demo: score the synthetic Dervio day and print the breakdown.

    pixi run demo
    # or:  mojo run -I src main.mojo

The output mirrors the Python reference demo (`python -m sailwise_ref.cli`) so the
two can be read side by side. If a number differs, one of the two implementations
is wrong — and mojo/tests/test_score.mojo will tell you which.
"""

from sailwise.fixture import dervio_synthetic_day
from sailwise.profiles import (
    profile_cruising,
    profile_family,
    profile_racing,
    profile_relax,
    profile_sport,
    profile_training,
)
from sailwise.score import (
    Accessibility,
    SailingProfile,
    ScoreResult,
    accessibility_unknown,
    sailing_score,
)
from sailwise.weather import (
    TREND_EASING,
    TREND_EASING_THEN_RISING,
    TREND_RISING,
    TREND_RISING_THEN_EASING,
    WindStats,
)

alias COMPONENT_NAMES = List[StaticString](
    "wind_quality",
    "wind_stability",
    "weather",
    "rain",
    "temperature",
    "water_conditions",
    "accessibility",
)


fn round2(x: Float64) -> Float64:
    """Two decimals, for display only. Never used in a comparison."""
    return Float64(Int(x * 100.0 + 0.5)) / 100.0


fn trend_name(code: Int) -> StaticString:
    if code == TREND_RISING:
        return "RISING"
    if code == TREND_EASING:
        return "EASING"
    if code == TREND_RISING_THEN_EASING:
        return "RISING_THEN_EASING"
    if code == TREND_EASING_THEN_RISING:
        return "EASING_THEN_RISING"
    return "STEADY"


fn print_result(name: StaticString, result: ScoreResult):
    print("---", name, "---")
    var w = result.wind
    print(
        "  wind: mean",
        round2(w.mean_kn),
        "kn | max",
        round2(w.max_kn),
        "| gust max",
        round2(w.gust_max_kn),
        "| sd",
        round2(w.stdev_kn),
    )
    print(
        "        gust factor",
        round2(w.gust_factor),
        "| consistency",
        round2(w.consistency),
        "| trend",
        trend_name(w.trend),
    )
    for i in range(len(result.raws)):
        if result.known[i]:
            print(
                "  ",
                COMPONENT_NAMES[i],
                ":",
                round2(result.points[i]),
                "/",
                round2(result.max_points[i]),
                " raw",
                round2(result.raws[i] * 1000.0) / 1000.0,
            )
        else:
            print("  ", COMPONENT_NAMES[i], ": UNKNOWN (excluded from aggregation)")
    print("   TOTAL:", round2(result.total), "/ 100  confidence", round2(result.confidence))
    print()


def main():
    var hours = dervio_synthetic_day()
    var access = accessibility_unknown()

    print("==============================================================")
    print("SAILWISE - Sailing Score (Milestone 1, Mojo compute core)")
    print("==============================================================")
    print("Spot  : Dervio (dervio)")
    print("Hours : 09:00-17:00")
    print("Data  : SYNTHETIC FIXTURE - not a forecast, not a real day")
    print()

    print_result("RELAX", sailing_score(hours, profile_relax(), access))
    print_result("CRUISING", sailing_score(hours, profile_cruising(), access))
    print_result("TRAINING", sailing_score(hours, profile_training(), access))
    print_result("RACING", sailing_score(hours, profile_racing(), access))
    print_result("FAMILY", sailing_score(hours, profile_family(), access))
    print_result("SPORT", sailing_score(hours, profile_sport(), access))

    print("Notes:")
    print("  - accessibility is UNKNOWN: no verified facility data ingested yet")
    print("  - water_conditions is ESTIMATED from wind speed, not a wave forecast")
    print()
    print("SailWise is decision support, not a safety clearance.")
    print("Always check official forecasts and notices before departure.")
