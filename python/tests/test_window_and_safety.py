"""Tests for the best-window search and the safety gates (Milestone 2).

The safety tests are the ones that must never be allowed to regress: they encode
FR-Z-01 and FR-Z-02, which are the difference between a planner and a liability.
"""

import pytest

from sailwise_ref.profiles import ProfileId, Weights, get_profile
from sailwise_ref.safety import Severity, evaluate_safety, is_recommended
from sailwise_ref.score import sailing_score
from sailwise_ref.weather import HourlyWeather
from sailwise_ref.window import best_window


def day(winds, gusts=None, storms=None, precip=None, start=9):
    n = len(winds)
    gusts = gusts or [w * 1.2 for w in winds]
    storms = storms or [0.0] * n
    precip = precip or [0.0] * n
    return [
        HourlyWeather(
            hour=start + i,
            wind_kn=winds[i],
            gust_kn=gusts[i],
            storm_prob=storms[i],
            precip_mm=precip[i],
        )
        for i in range(n)
    ]


CRUISING = get_profile(ProfileId.CRUISING)  # band 4, 8, 16, 22; gust limit 22


# --- best window -----------------------------------------------------------


def test_window_picks_the_windy_part_of_the_day():
    hours = day([2, 3, 10, 12, 13, 12, 3, 2])  # good from 11:00 to 14:00 inclusive
    result = best_window(hours, CRUISING, min_duration_h=2)
    assert result.window is not None
    assert result.window.start_hour == 11
    assert result.window.end_hour == 15


def test_window_prefers_the_longer_window_when_quality_ties():
    """Maximising a mean alone would return the shortest allowed window."""
    hours = day([12.0] * 6)
    result = best_window(hours, CRUISING, min_duration_h=2)
    assert result.window is not None
    assert result.window.duration_h == 6
    assert result.window.start_hour == 9


def test_window_never_spans_an_excluded_hour():
    # 13:00 has gusts of 30 kn, above the 22 kn CRUISING limit.
    hours = day([12, 12, 12, 12, 12, 12], gusts=[14, 14, 14, 14, 30, 14])
    result = best_window(hours, CRUISING, min_duration_h=2)
    assert result.window is not None
    hours_in_window = range(result.window.start_hour, result.window.end_hour)
    assert 13 not in hours_in_window
    assert [h.hour for h in result.excluded_hours] == [13]


def test_window_returns_none_when_nothing_is_admissible():
    hours = day([12] * 5, gusts=[40] * 5)
    result = best_window(hours, CRUISING, min_duration_h=2)
    assert result.window is None
    assert result.note is not None
    assert len(result.excluded_hours) == 5


def test_window_returns_none_when_the_day_is_too_short():
    result = best_window(day([12, 12]), CRUISING, min_duration_h=5)
    assert result.window is None
    assert "shorter than" in result.note


def test_window_requires_a_forecast():
    with pytest.raises(ValueError):
        best_window([], CRUISING)


# --- safety gates ----------------------------------------------------------


def test_no_warnings_on_a_benign_day():
    report = evaluate_safety(day([10, 11, 12, 11, 10]), CRUISING)
    assert report.warnings == []
    assert report.return_by_label is None
    assert not report.has_critical


def test_gust_above_limit_is_a_caution_with_a_return_time():
    hours = day([12, 13, 14, 15, 16], gusts=[14, 15, 16, 24, 25])
    report = evaluate_safety(hours, CRUISING)
    codes = [w.code for w in report.warnings]
    assert "GUST_ABOVE_LIMIT" in codes
    # first offending hour is 12:00, minus the 30 minute margin
    assert report.return_by_label == "11:30"


def test_far_above_limit_escalates_to_critical():
    hours = day([12, 13, 14], gusts=[14, 15, 40])
    report = evaluate_safety(hours, CRUISING)
    assert "GUST_FAR_ABOVE_LIMIT" in [w.code for w in report.warnings]
    assert report.has_critical
    assert report.worst_severity is Severity.CRITICAL


def test_thunderstorm_thresholds():
    caution = evaluate_safety(day([12] * 4, storms=[0.0, 0.35, 0.35, 0.0]), CRUISING)
    assert "THUNDERSTORM_RISK" in [w.code for w in caution.warnings]
    assert not caution.has_critical

    critical = evaluate_safety(day([12] * 4, storms=[0.0, 0.6, 0.6, 0.0]), CRUISING)
    assert "THUNDERSTORM_LIKELY" in [w.code for w in critical.warnings]
    assert critical.has_critical


def test_low_visibility_is_critical():
    hours = day([12] * 3)
    hours[1] = HourlyWeather(hour=10, wind_kn=12, gust_kn=14, visibility_m=500.0)
    report = evaluate_safety(hours, CRUISING)
    assert "VISIBILITY_LOW" in [w.code for w in report.warnings]
    assert report.has_critical


def test_unknown_visibility_produces_no_visibility_warning():
    """Missing data is not good news and not bad news. It is missing."""
    hours = [HourlyWeather(hour=9 + i, wind_kn=12, gust_kn=14, visibility_m=None) for i in range(4)]
    report = evaluate_safety(hours, CRUISING)
    assert not any(w.code.startswith("VISIBILITY") for w in report.warnings)


def test_rapid_wind_increase_is_flagged():
    report = evaluate_safety(day([6, 7, 16, 17]), CRUISING)
    assert "RAPID_WIND_INCREASE" in [w.code for w in report.warnings]


def test_insufficient_wind_is_info_not_a_warning_to_act_on():
    report = evaluate_safety(day([1, 1, 2, 1]), CRUISING)
    codes = {w.code: w.severity for w in report.warnings}
    assert codes["INSUFFICIENT_WIND"] is Severity.INFO
    assert not report.has_critical


# --- the separation guarantee (FR-Z-01, FR-Z-02) ---------------------------


def test_warnings_are_independent_of_the_weight_configuration():
    """No weight set can make a warning disappear."""
    hours = day([12, 13, 14], gusts=[14, 15, 40])
    baseline = evaluate_safety(hours, CRUISING)

    # A profile that cares about nothing except temperature.
    absurd = type(CRUISING)(
        id=CRUISING.id,
        weights=Weights(0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        wind_band_kn=CRUISING.wind_band_kn,
        temp_band_c=CRUISING.temp_band_c,
        chop_sensitivity=CRUISING.chop_sensitivity,
        gust_limit_kn=CRUISING.gust_limit_kn,
    )
    tweaked = evaluate_safety(hours, absurd)
    assert [w.code for w in tweaked.warnings] == [w.code for w in baseline.warnings]


def test_a_high_score_cannot_override_a_critical_warning():
    # A near-perfect day, except for a thunderstorm.
    hours = day([12] * 6, storms=[0.0, 0.0, 0.0, 0.7, 0.7, 0.0])
    score = sailing_score(hours, CRUISING)
    report = evaluate_safety(hours, CRUISING)
    assert report.has_critical
    assert not is_recommended(score.total, report)
    # even at a hypothetical perfect score
    assert not is_recommended(100.0, report)


def test_disclaimer_is_always_present():
    report = evaluate_safety(day([10, 11, 12]), CRUISING)
    assert "not a safety clearance" in report.disclaimer
    assert "official" in report.as_dict()["disclaimer"]
