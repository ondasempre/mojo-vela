"""Tests for the Sailing Score, including the cross-language golden check.

The golden test (NFR-C-01) is the one that matters most in this repository: it pins
the Mojo implementation to the Python reference within 1e-9. Every future
optimisation — SIMD, parallel, layout changes — has to keep passing it, which is
what makes optimising safe.

Run:  mojo run -I src -I tests tests/test_score.mojo
"""

from std.testing import TestSuite, assert_almost_equal, assert_equal, assert_true

from golden_values import (
    GOLDEN_CRUISING_RAIN,
    GOLDEN_CRUISING_TEMPERATURE,
    GOLDEN_CRUISING_WATER_CONDITIONS,
    GOLDEN_CRUISING_WEATHER,
    GOLDEN_CRUISING_WIND_QUALITY,
    GOLDEN_CRUISING_WIND_STABILITY,
    GOLDEN_TOLERANCE,
    GOLDEN_TOTAL_CRUISING,
    GOLDEN_TOTAL_FAMILY,
    GOLDEN_TOTAL_RACING,
    GOLDEN_TOTAL_RELAX,
    GOLDEN_TOTAL_SPORT,
    GOLDEN_TOTAL_TRAINING,
    GOLDEN_WIND_CONSISTENCY,
    GOLDEN_WIND_CV,
    GOLDEN_WIND_GUST_FACTOR,
    GOLDEN_WIND_GUST_MAX_KN,
    GOLDEN_WIND_MAX_KN,
    GOLDEN_WIND_MEAN_KN,
    GOLDEN_WIND_STDEV_KN,
)
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
    C_ACCESSIBILITY,
    C_WIND_QUALITY,
    C_WIND_STABILITY,
    N_COMPONENTS,
    SailingProfile,
    Weights,
    accessibility_unknown,
    sailing_score,
    score_accessibility,
)
from sailwise.weather import HourlyWeather, compute_wind_stats, fair_hour


fn flat_day(wind: Float64, gust_ratio: Float64 = 1.2) -> List[HourlyWeather]:
    var hours = List[HourlyWeather]()
    for i in range(8):
        hours.append(fair_hour(9 + i, wind, wind * gust_ratio))
    return hours


# --- the golden cross-language test ----------------------------------------


def test_golden_wind_stats_match_the_python_reference():
    var hours = dervio_synthetic_day()
    var s = compute_wind_stats(hours)
    assert_almost_equal(s.mean_kn, GOLDEN_WIND_MEAN_KN, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.max_kn, GOLDEN_WIND_MAX_KN, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.gust_max_kn, GOLDEN_WIND_GUST_MAX_KN, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.stdev_kn, GOLDEN_WIND_STDEV_KN, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.cv, GOLDEN_WIND_CV, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.gust_factor, GOLDEN_WIND_GUST_FACTOR, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(s.consistency, GOLDEN_WIND_CONSISTENCY, atol=GOLDEN_TOLERANCE)


def test_golden_totals_match_the_python_reference():
    var hours = dervio_synthetic_day()
    var access = accessibility_unknown()
    assert_almost_equal(
        sailing_score(hours, profile_relax(), access).total,
        GOLDEN_TOTAL_RELAX,
        atol=GOLDEN_TOLERANCE,
    )
    assert_almost_equal(
        sailing_score(hours, profile_cruising(), access).total,
        GOLDEN_TOTAL_CRUISING,
        atol=GOLDEN_TOLERANCE,
    )
    assert_almost_equal(
        sailing_score(hours, profile_training(), access).total,
        GOLDEN_TOTAL_TRAINING,
        atol=GOLDEN_TOLERANCE,
    )
    assert_almost_equal(
        sailing_score(hours, profile_racing(), access).total,
        GOLDEN_TOTAL_RACING,
        atol=GOLDEN_TOLERANCE,
    )
    assert_almost_equal(
        sailing_score(hours, profile_family(), access).total,
        GOLDEN_TOTAL_FAMILY,
        atol=GOLDEN_TOLERANCE,
    )
    assert_almost_equal(
        sailing_score(hours, profile_sport(), access).total,
        GOLDEN_TOTAL_SPORT,
        atol=GOLDEN_TOLERANCE,
    )


def test_golden_components_match_the_python_reference():
    var r = sailing_score(dervio_synthetic_day(), profile_cruising(), accessibility_unknown())
    assert_almost_equal(r.raws[0], GOLDEN_CRUISING_WIND_QUALITY, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(r.raws[1], GOLDEN_CRUISING_WIND_STABILITY, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(r.raws[2], GOLDEN_CRUISING_WEATHER, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(r.raws[3], GOLDEN_CRUISING_RAIN, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(r.raws[4], GOLDEN_CRUISING_TEMPERATURE, atol=GOLDEN_TOLERANCE)
    assert_almost_equal(r.raws[5], GOLDEN_CRUISING_WATER_CONDITIONS, atol=GOLDEN_TOLERANCE)
    assert_true(not r.known[C_ACCESSIBILITY])


# --- contract properties ---------------------------------------------------


def test_score_is_always_within_range():
    var access = accessibility_unknown()
    var winds = List[Float64](0.0, 1.0, 5.0, 12.0, 20.0, 35.0, 60.0)
    for i in range(len(winds)):
        for p in range(6):
            var r = sailing_score(flat_day(winds[i]), get_profile_by_index(p), access)
            assert_true(r.total >= 0.0 and r.total <= 100.0)
            for c in range(N_COMPONENTS):
                if r.known[c]:
                    assert_true(r.raws[c] >= 0.0 and r.raws[c] <= 1.0)


def test_score_is_deterministic():
    var hours = flat_day(11.0)
    var access = accessibility_unknown()
    var a = sailing_score(hours, profile_cruising(), access)
    var b = sailing_score(hours, profile_cruising(), access)
    assert_equal(a.total, b.total)


def test_scaling_all_weights_leaves_the_score_unchanged():
    """FR-S-05: weights are ratios, so an edited set that does not sum to 1 is safe."""
    var base = profile_cruising()
    var scaled = SailingProfile(
        Weights(
            base.weights.wind_quality * 7.3,
            base.weights.wind_stability * 7.3,
            base.weights.weather * 7.3,
            base.weights.rain * 7.3,
            base.weights.temperature * 7.3,
            base.weights.water_conditions * 7.3,
            base.weights.accessibility * 7.3,
        ),
        base.wind_band_kn,
        base.temp_band_c,
        base.chop_sensitivity,
        base.gust_limit_kn,
    )
    var hours = flat_day(11.0)
    var access = accessibility_unknown()
    assert_almost_equal(
        sailing_score(hours, base, access).total,
        sailing_score(hours, scaled, access).total,
        atol=1e-12,
    )


def test_component_points_sum_to_total():
    var r = sailing_score(flat_day(11.0), profile_cruising(), accessibility_unknown())
    var total: Float64 = 0.0
    for i in range(N_COMPONENTS):
        total += r.points[i]
    assert_almost_equal(total, r.total, atol=1e-12)


def test_steady_wind_beats_variable_wind_with_the_same_mean():
    var steady = List[HourlyWeather]()
    var variable = List[HourlyWeather]()
    for i in range(8):
        steady.append(fair_hour(9 + i, 12.0, 14.0))
        if i % 2 == 0:
            variable.append(fair_hour(9 + i, 18.0, 22.0))
        else:
            variable.append(fair_hour(9 + i, 6.0, 22.0))

    var access = accessibility_unknown()
    var a = sailing_score(steady, profile_cruising(), access)
    var b = sailing_score(variable, profile_cruising(), access)
    assert_true(a.raws[C_WIND_STABILITY] > b.raws[C_WIND_STABILITY])
    assert_true(a.total > b.total)


def test_profiles_disagree_about_the_same_day():
    """A 20 kn day is a bad family outing and a good sport day. That is the point."""
    var hours = flat_day(20.0)
    var access = accessibility_unknown()
    var family = sailing_score(hours, profile_family(), access)
    var sport = sailing_score(hours, profile_sport(), access)
    assert_true(sport.total > family.total)
    assert_equal(family.raws[C_WIND_QUALITY], 0.0)


# --- UNKNOWN handling (FR-P-03) --------------------------------------------


def test_unknown_accessibility_is_excluded_not_zeroed():
    var hours = flat_day(12.0)
    var unknown = sailing_score(hours, profile_cruising(), accessibility_unknown())
    var zero = sailing_score(
        hours,
        profile_cruising(),
        Accessibility(0.0, True, 0.0, True, 0.0, True, 0.0, True),
    )
    assert_true(not unknown.known[C_ACCESSIBILITY])
    assert_true(zero.known[C_ACCESSIBILITY])
    # "we don't know" must not be punished like "it's terrible"
    assert_true(unknown.total > zero.total)
    assert_true(unknown.confidence < 1.0)
    assert_almost_equal(zero.confidence, 1.0, atol=1e-12)


def test_partial_accessibility_data_is_renormalised():
    var only_launch = Accessibility(1.0, True, 0.0, False, 0.0, False, 0.0, False)
    var result = score_accessibility(only_launch)
    assert_almost_equal(result[0], 1.0, atol=1e-12)  # not 0.40: missing factors drop out
    assert_true(result[1])
    assert_almost_equal(result[2], 0.40, atol=1e-12)  # confidence records what was missing


def test_empty_forecast_is_rejected():
    var empty = List[HourlyWeather]()
    var raised = False
    try:
        _ = sailing_score(empty, profile_cruising(), accessibility_unknown())
    except:
        raised = True
    assert_true(raised)


# --- helpers ---------------------------------------------------------------


fn get_profile_by_index(index: Int) -> SailingProfile:
    if index == 0:
        return profile_relax()
    if index == 1:
        return profile_cruising()
    if index == 2:
        return profile_training()
    if index == 3:
        return profile_racing()
    if index == 4:
        return profile_family()
    return profile_sport()


def main() raises:
    TestSuite.discover_tests[__functions_in_module()]().run()
