"""Tests for the wind statistics.

Run:  mojo run -I src tests/test_wind.mojo
"""

from std.testing import TestSuite, assert_almost_equal, assert_equal, assert_true

from sailwise.weather import (
    TREND_EASING,
    TREND_RISING,
    TREND_RISING_THEN_EASING,
    TREND_STEADY,
    compute_wind_stats,
    fair_hour,
    HourlyWeather,
)

alias TOL: Float64 = 1e-12


fn series(speeds: List[Float64], gust_ratio: Float64 = 1.3) -> List[HourlyWeather]:
    var hours = List[HourlyWeather]()
    for i in range(len(speeds)):
        hours.append(fair_hour(9 + i, speeds[i], speeds[i] * gust_ratio))
    return hours


def test_basic_statistics():
    var s = compute_wind_stats(series(List[Float64](10.0, 10.0, 10.0, 10.0)))
    assert_almost_equal(s.mean_kn, 10.0, atol=TOL)
    assert_almost_equal(s.max_kn, 10.0, atol=TOL)
    assert_almost_equal(s.min_kn, 10.0, atol=TOL)
    assert_almost_equal(s.stdev_kn, 0.0, atol=TOL)
    assert_almost_equal(s.cv, 0.0, atol=TOL)
    assert_almost_equal(s.consistency, 1.0, atol=TOL)
    assert_almost_equal(s.gust_factor, 1.3, atol=1e-12)


def test_calm_does_not_divide_by_zero():
    """The MEAN_WIND_FLOOR guard: near-calm must not produce nan or inf."""
    var s = compute_wind_stats(series(List[Float64](0.0, 0.1, 0.0, 0.2)))
    assert_equal(s.cv, 1.0)
    assert_equal(s.gust_factor, 1.0)
    assert_equal(s.consistency, 0.0)
    assert_almost_equal(s.mean_kn, 0.075, atol=TOL)


def test_variance_lowers_consistency():
    var steady = compute_wind_stats(series(List[Float64](12.0, 12.0, 12.0, 12.0)))
    var gusty = compute_wind_stats(series(List[Float64](4.0, 20.0, 4.0, 20.0)))
    assert_almost_equal(steady.mean_kn, gusty.mean_kn, atol=TOL)
    assert_true(steady.consistency > gusty.consistency)


def test_min_and_max_are_found():
    var s = compute_wind_stats(series(List[Float64](8.0, 3.0, 19.0, 11.0)))
    assert_almost_equal(s.min_kn, 3.0, atol=TOL)
    assert_almost_equal(s.max_kn, 19.0, atol=TOL)
    assert_almost_equal(s.gust_max_kn, 19.0 * 1.3, atol=1e-12)


def test_trend_rising_and_easing():
    assert_equal(compute_wind_stats(series(List[Float64](4.0, 7.0, 10.0, 13.0))).trend, TREND_RISING)
    assert_equal(compute_wind_stats(series(List[Float64](13.0, 10.0, 7.0, 4.0))).trend, TREND_EASING)
    assert_equal(compute_wind_stats(series(List[Float64](9.0, 9.1, 9.0, 8.9))).trend, TREND_STEADY)


def test_thermal_day_is_detected():
    """A lake thermal builds then dies; a single overall slope would call it steady."""
    var s = compute_wind_stats(series(List[Float64](5.0, 9.0, 13.0, 15.0, 13.0, 9.0, 5.0)))
    assert_equal(s.trend, TREND_RISING_THEN_EASING)
    assert_true(s.slope_kn_per_h < 0.5 and s.slope_kn_per_h > -0.5)


def test_empty_series_is_rejected():
    var empty = List[HourlyWeather]()
    var raised = False
    try:
        _ = compute_wind_stats(empty)
    except:
        raised = True
    assert_true(raised)


def main() raises:
    TestSuite.discover_tests[__functions_in_module()]().run()
