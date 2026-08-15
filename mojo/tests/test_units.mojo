"""Unit tests for the numeric primitives.

Run:  mojo run -I src tests/test_units.mojo   (or: pixi run test)
"""

from std.testing import TestSuite, assert_almost_equal, assert_equal, assert_true

from sailwise.units import (
    clamp01,
    km_to_nm,
    kmh_to_kn,
    least_squares_slope,
    mean,
    ms_to_kn,
    stdev_population,
    trapezoid,
)

alias TOL: Float64 = 1e-12


def test_clamp01_bounds():
    assert_equal(clamp01(-5.0), 0.0)
    assert_equal(clamp01(0.0), 0.0)
    assert_equal(clamp01(0.4), 0.4)
    assert_equal(clamp01(1.0), 1.0)
    assert_equal(clamp01(12.0), 1.0)


def test_trapezoid_cruising_band():
    # CRUISING wind band: 4, 8, 16, 22
    assert_equal(trapezoid(2.0, 4.0, 8.0, 16.0, 22.0), 0.0)
    assert_equal(trapezoid(4.0, 4.0, 8.0, 16.0, 22.0), 0.0)
    assert_almost_equal(trapezoid(5.0, 4.0, 8.0, 16.0, 22.0), 0.25, atol=TOL)
    assert_almost_equal(trapezoid(6.0, 4.0, 8.0, 16.0, 22.0), 0.5, atol=TOL)
    assert_equal(trapezoid(8.0, 4.0, 8.0, 16.0, 22.0), 1.0)
    assert_equal(trapezoid(12.0, 4.0, 8.0, 16.0, 22.0), 1.0)
    assert_equal(trapezoid(16.0, 4.0, 8.0, 16.0, 22.0), 1.0)
    assert_almost_equal(trapezoid(19.0, 4.0, 8.0, 16.0, 22.0), 0.5, atol=TOL)
    assert_equal(trapezoid(22.0, 4.0, 8.0, 16.0, 22.0), 0.0)
    assert_equal(trapezoid(30.0, 4.0, 8.0, 16.0, 22.0), 0.0)


def test_trapezoid_degenerate_edges_do_not_divide_by_zero():
    # A band with no ramps is a rectangle. This must not produce inf or nan.
    assert_equal(trapezoid(5.0, 5.0, 5.0, 10.0, 10.0), 0.0)
    assert_equal(trapezoid(7.0, 5.0, 5.0, 10.0, 10.0), 1.0)
    assert_equal(trapezoid(10.0, 5.0, 5.0, 10.0, 10.0), 0.0)


def test_trapezoid_stays_in_unit_interval():
    for i in range(-50, 100):
        var v = trapezoid(Float64(i), 4.0, 8.0, 16.0, 22.0)
        assert_true(v >= 0.0 and v <= 1.0)


def test_mean_and_stdev():
    var values = List[Float64](2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0)
    assert_almost_equal(mean(values), 5.0, atol=TOL)
    # Population standard deviation (divides by n) is exactly 2.0 here.
    assert_almost_equal(stdev_population(values), 2.0, atol=TOL)


def test_stdev_of_constant_series_is_zero():
    var values = List[Float64](7.0, 7.0, 7.0, 7.0)
    assert_equal(stdev_population(values), 0.0)


def test_mean_of_empty_list_is_zero_not_a_crash():
    var empty = List[Float64]()
    assert_equal(mean(empty), 0.0)
    assert_equal(stdev_population(empty), 0.0)


def test_least_squares_slope():
    assert_almost_equal(least_squares_slope(List[Float64](1.0, 2.0, 3.0, 4.0)), 1.0, atol=TOL)
    assert_almost_equal(least_squares_slope(List[Float64](4.0, 3.0, 2.0, 1.0)), -1.0, atol=TOL)
    assert_almost_equal(least_squares_slope(List[Float64](5.0, 5.0, 5.0)), 0.0, atol=TOL)
    assert_equal(least_squares_slope(List[Float64](5.0)), 0.0)


def test_unit_conversions():
    assert_almost_equal(ms_to_kn(1.0), 1.943844492440605, atol=TOL)
    assert_almost_equal(kmh_to_kn(3.6), ms_to_kn(1.0), atol=1e-9)
    assert_almost_equal(km_to_nm(1.852), 1.0, atol=TOL)


def main() raises:
    TestSuite.discover_tests[__functions_in_module()]().run()
