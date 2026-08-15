import pytest

from sailwise_ref.units import (
    clamp01,
    km_to_nm,
    kmh_to_kn,
    least_squares_slope,
    ms_to_kn,
    stdev_population,
    trapezoid,
)


def test_clamp01_bounds():
    assert clamp01(-5.0) == 0.0
    assert clamp01(0.0) == 0.0
    assert clamp01(0.4) == 0.4
    assert clamp01(1.0) == 1.0
    assert clamp01(12.0) == 1.0


@pytest.mark.parametrize(
    "x,expected",
    [
        (3.0, 0.0),  # at a
        (2.0, 0.0),  # below a
        (5.0, 0.25),  # ramping up: (5-4)/(8-4)
        (6.0, 0.5),
        (8.0, 1.0),  # start of plateau
        (12.0, 1.0),  # inside plateau
        (16.0, 1.0),  # end of plateau
        (19.0, 0.5),  # ramping down: (22-19)/(22-16)
        (22.0, 0.0),  # at d
        (30.0, 0.0),  # above d
    ],
)
def test_trapezoid_cruising_band(x, expected):
    # CRUISING wind band: 4, 8, 16, 22
    assert trapezoid(x, 4.0, 8.0, 16.0, 22.0) == pytest.approx(expected)


def test_trapezoid_degenerate_edges_do_not_divide_by_zero():
    # A band with no ramps is a rectangle, and must not raise.
    assert trapezoid(5.0, 5.0, 5.0, 10.0, 10.0) == 0.0
    assert trapezoid(7.0, 5.0, 5.0, 10.0, 10.0) == 1.0
    assert trapezoid(10.0, 5.0, 5.0, 10.0, 10.0) == 0.0


def test_trapezoid_is_never_outside_unit_interval():
    for x in range(-50, 100):
        v = trapezoid(float(x), 4.0, 8.0, 16.0, 22.0)
        assert 0.0 <= v <= 1.0


def test_stdev_population_is_n_not_n_minus_1():
    # population sd of [2, 4, 4, 4, 5, 5, 7, 9] is exactly 2.0
    assert stdev_population([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.0)


def test_stdev_of_constant_series_is_zero():
    assert stdev_population([7.0] * 10) == 0.0


def test_least_squares_slope():
    assert least_squares_slope([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)
    assert least_squares_slope([4.0, 3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    assert least_squares_slope([5.0, 5.0, 5.0]) == pytest.approx(0.0)
    assert least_squares_slope([5.0]) == 0.0


def test_unit_conversions_round_trip():
    assert ms_to_kn(1.0) == pytest.approx(1.9438444924406047)
    assert kmh_to_kn(3.6) == pytest.approx(ms_to_kn(1.0))
    assert km_to_nm(1.852) == pytest.approx(1.0)
