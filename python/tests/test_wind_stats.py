import pytest

from sailwise_ref.weather import HourlyWeather, WindTrend, wind_stats


def series(speeds, gusts=None):
    gusts = gusts or [s * 1.3 for s in speeds]
    return [
        HourlyWeather(hour=9 + i, wind_kn=s, gust_kn=g)
        for i, (s, g) in enumerate(zip(speeds, gusts, strict=True))
    ]


def test_basic_statistics():
    s = wind_stats(series([10.0, 10.0, 10.0, 10.0]))
    assert s.mean_kn == pytest.approx(10.0)
    assert s.max_kn == pytest.approx(10.0)
    assert s.min_kn == pytest.approx(10.0)
    assert s.stdev_kn == pytest.approx(0.0)
    assert s.cv == pytest.approx(0.0)
    assert s.consistency == pytest.approx(1.0)
    assert s.gust_factor == pytest.approx(1.3)


def test_calm_does_not_divide_by_zero():
    """The MEAN_WIND_FLOOR guard: near-calm must not produce NaN or an exception."""
    s = wind_stats(series([0.0, 0.1, 0.0, 0.2]))
    assert s.cv == 1.0
    assert s.gust_factor == 1.0
    assert s.consistency == 0.0
    assert s.mean_kn == pytest.approx(0.075)


def test_variance_lowers_consistency():
    steady = wind_stats(series([12.0, 12.0, 12.0, 12.0]))
    gusty = wind_stats(series([4.0, 20.0, 4.0, 20.0]))
    assert steady.mean_kn == pytest.approx(gusty.mean_kn)
    assert steady.consistency > gusty.consistency


def test_trend_rising_and_easing():
    assert wind_stats(series([4.0, 7.0, 10.0, 13.0])).trend == WindTrend.RISING
    assert wind_stats(series([13.0, 10.0, 7.0, 4.0])).trend == WindTrend.EASING
    assert wind_stats(series([9.0, 9.1, 9.0, 8.9])).trend == WindTrend.STEADY


def test_trend_thermal_day_is_detected():
    """A lake thermal builds then dies; a single overall slope would call it steady."""
    s = wind_stats(series([5.0, 9.0, 13.0, 15.0, 13.0, 9.0, 5.0]))
    assert s.trend == WindTrend.RISING_THEN_EASING
    assert abs(s.slope_kn_per_h) < 0.5  # the overall slope really is ~flat


def test_empty_series_is_rejected():
    with pytest.raises(ValueError):
        wind_stats([])
