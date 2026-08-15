"""Tests for the Sailing Score.

The property tests here are the ones that must survive every future optimisation:
they encode the model's contract, not its current numbers.
"""

import pytest

from sailwise_ref.fixtures import load_day
from sailwise_ref.profiles import PROFILES, ProfileId, Weights, get_profile
from sailwise_ref.score import AccessibilityInput, sailing_score, score_accessibility
from sailwise_ref.weather import HourlyWeather


def flat_day(wind=12.0, gust=None, **kw):
    gust = gust if gust is not None else wind * 1.2
    return [HourlyWeather(hour=9 + i, wind_kn=wind, gust_kn=gust, **kw) for i in range(8)]


# --- range and determinism -------------------------------------------------


@pytest.mark.parametrize("profile_id", list(ProfileId))
@pytest.mark.parametrize("wind", [0.0, 1.0, 5.0, 12.0, 20.0, 35.0, 60.0])
def test_score_is_always_within_range(profile_id, wind):
    result = sailing_score(flat_day(wind), get_profile(profile_id))
    assert 0.0 <= result.total <= 100.0
    for c in result.components:
        if c.raw is not None:
            assert 0.0 <= c.raw <= 1.0


def test_score_is_deterministic():
    day = flat_day(11.0)
    profile = get_profile(ProfileId.CRUISING)
    a = sailing_score(day, profile)
    b = sailing_score(day, profile)
    assert a.total == b.total
    assert [c.points for c in a.components] == [c.points for c in b.components]


def test_empty_forecast_is_rejected():
    with pytest.raises(ValueError):
        sailing_score([], get_profile(ProfileId.CRUISING))


# --- aggregation contract --------------------------------------------------


def test_scaling_all_weights_leaves_the_score_unchanged():
    """FR-S-05: weights are ratios, so a user-edited set that does not sum to 1 is safe."""
    base = get_profile(ProfileId.CRUISING)
    scaled_weights = Weights(*[w * 7.3 for w in base.weights.as_tuple()])
    scaled = type(base)(
        id=base.id,
        weights=scaled_weights,
        wind_band_kn=base.wind_band_kn,
        temp_band_c=base.temp_band_c,
        chop_sensitivity=base.chop_sensitivity,
        gust_limit_kn=base.gust_limit_kn,
    )
    day = flat_day(11.0)
    assert sailing_score(day, base).total == pytest.approx(
        sailing_score(day, scaled).total, abs=1e-12
    )


def test_component_points_sum_to_total():
    result = sailing_score(flat_day(11.0), get_profile(ProfileId.CRUISING))
    assert sum(c.points for c in result.components) == pytest.approx(result.total)


def test_max_points_sum_to_100():
    result = sailing_score(flat_day(11.0), get_profile(ProfileId.CRUISING))
    available = [c for c in result.components if c.raw is not None]
    assert sum(c.max_points for c in available) == pytest.approx(100.0)


# --- component behaviour ---------------------------------------------------


def test_wind_in_band_beats_wind_outside_band():
    profile = get_profile(ProfileId.CRUISING)  # band 4, 8, 16, 22
    good = sailing_score(flat_day(12.0), profile)
    calm = sailing_score(flat_day(1.0), profile)
    storm = sailing_score(flat_day(35.0), profile)
    assert good.total > calm.total
    assert good.total > storm.total
    assert calm.component("wind_quality").raw == 0.0
    assert storm.component("wind_quality").raw == 0.0


def test_steady_wind_scores_higher_than_variable_wind_with_the_same_mean():
    profile = get_profile(ProfileId.CRUISING)
    steady = [HourlyWeather(hour=9 + i, wind_kn=12.0, gust_kn=14.0) for i in range(8)]
    variable = [
        HourlyWeather(hour=9 + i, wind_kn=(6.0 if i % 2 else 18.0), gust_kn=22.0)
        for i in range(8)
    ]
    assert sum(h.wind_kn for h in steady) == sum(h.wind_kn for h in variable)
    a, b = sailing_score(steady, profile), sailing_score(variable, profile)
    assert a.component("wind_stability").raw > b.component("wind_stability").raw
    assert a.total > b.total


def test_rain_reduces_the_rain_component():
    profile = get_profile(ProfileId.CRUISING)
    dry = sailing_score(flat_day(12.0), profile)
    wet = sailing_score(flat_day(12.0, precip_mm=1.0, precip_prob=0.9), profile)
    assert dry.component("rain").raw == pytest.approx(1.0)
    assert wet.component("rain").raw == 0.0
    assert wet.total < dry.total


def test_thunderstorm_reduces_the_weather_component():
    profile = get_profile(ProfileId.CRUISING)
    clear = sailing_score(flat_day(12.0), profile)
    stormy = sailing_score(flat_day(12.0, storm_prob=0.8), profile)
    assert stormy.component("weather").raw < clear.component("weather").raw


def test_profiles_disagree_about_the_same_day():
    """A 20 kn day is a bad family outing and a good sport day. That is the point."""
    day = flat_day(20.0, gust=24.0)
    family = sailing_score(day, get_profile(ProfileId.FAMILY))
    sport = sailing_score(day, get_profile(ProfileId.SPORT))
    assert sport.total > family.total
    assert family.component("wind_quality").raw == 0.0


def test_every_profile_produces_a_score_for_the_fixture_day():
    day = load_day()
    for profile in PROFILES.values():
        result = sailing_score(day.hours, profile, day.accessibility)
        assert 0.0 <= result.total <= 100.0


# --- UNKNOWN handling (FR-P-03) --------------------------------------------


def test_unknown_accessibility_is_excluded_not_zeroed():
    profile = get_profile(ProfileId.CRUISING)
    day = flat_day(12.0)
    unknown = sailing_score(day, profile, AccessibilityInput())
    zero = sailing_score(
        day, profile, AccessibilityInput(launch=0.0, parking=0.0, drive=0.0, services=0.0)
    )
    assert unknown.component("accessibility").raw is None
    assert zero.component("accessibility").raw == 0.0
    # "we don't know" must not be punished like "it's terrible"
    assert unknown.total > zero.total
    # but it must be visible in the confidence
    assert unknown.confidence < 1.0
    assert zero.confidence == pytest.approx(1.0)


def test_partial_accessibility_data_is_renormalised():
    raw, confidence = score_accessibility(AccessibilityInput(launch=1.0))
    assert raw == pytest.approx(1.0)  # not 0.40 — the missing factors drop out
    assert confidence == pytest.approx(0.40)  # and confidence records what was missing


def test_accessibility_all_unknown_reports_zero_confidence():
    raw, confidence = score_accessibility(AccessibilityInput())
    assert raw is None
    assert confidence == 0.0
