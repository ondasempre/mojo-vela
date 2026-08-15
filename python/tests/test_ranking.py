"""Tests for multi-spot ranking (Milestone 3)."""

import pytest

from sailwise_ref.profiles import ProfileId, get_profile
from sailwise_ref.ranking import (
    SpotInput,
    affinity_for,
    estimate_drive,
    explain_pair,
    haversine_km,
    rank_spots,
)
from sailwise_ref.score import AccessibilityInput
from sailwise_ref.weather import HourlyWeather

CRUISING = get_profile(ProfileId.CRUISING)


def hours(wind, gust=None, n=8):
    gust = gust if gust is not None else wind * 1.2
    return [HourlyWeather(hour=9 + i, wind_kn=wind, gust_kn=gust) for i in range(n)]


def spot(spot_id, wind, **kw):
    return SpotInput(id=spot_id, name=spot_id.title(), lat=kw.pop("lat", None),
                     lon=kw.pop("lon", None), hours=hours(wind), **kw)


# --- geometry --------------------------------------------------------------


def test_haversine_against_a_known_distance():
    # One degree of latitude is about 111.2 km anywhere on the globe.
    assert haversine_km(45.0, 9.0, 46.0, 9.0) == pytest.approx(111.19, abs=0.1)


def test_haversine_is_symmetric_and_zero_for_the_same_point():
    assert haversine_km(45.0, 9.0, 45.0, 9.0) == 0.0
    assert haversine_km(45.0, 9.0, 46.0, 10.0) == pytest.approx(
        haversine_km(46.0, 10.0, 45.0, 9.0)
    )


def test_drive_estimate_is_labelled_as_an_estimate():
    d = estimate_drive((45.0, 9.0), 46.0, 9.0)
    assert d is not None
    assert d.provenance == "ESTIMATED"
    assert d.km > 111.0  # detour factor applied
    assert d.minutes > 0


def test_drive_estimate_is_none_without_coordinates():
    assert estimate_drive(None, 46.0, 9.0) is None
    assert estimate_drive((45.0, 9.0), None, None) is None


# --- affinity --------------------------------------------------------------


def test_affinity_without_history_is_the_prior():
    assert affinity_for(None, 0) == pytest.approx(0.55)
    assert affinity_for(9.0, 0) == pytest.approx(0.55)


def test_one_good_visit_does_not_crown_a_spot():
    """Shrinkage: a single 9/10 gives 0.64, not 0.90."""
    assert affinity_for(9.0, 1) == pytest.approx((1 * 0.9 + 3 * 0.55) / 4)


def test_affinity_converges_with_more_visits():
    assert affinity_for(9.0, 50) > affinity_for(9.0, 5) > affinity_for(9.0, 1)


# --- ranking ---------------------------------------------------------------


def test_better_conditions_rank_higher():
    result = rank_spots(
        [spot("good", 12.0), spot("calm", 1.0), spot("gale", 40.0)], CRUISING
    )
    assert [r.spot.id for r in result.results][0] == "good"
    assert result.results[0].rank_score > result.results[-1].rank_score


def test_driving_limit_excludes_with_a_reason():
    far = SpotInput(id="far", name="Far", lat=47.0, lon=9.0, hours=hours(12.0))
    near = SpotInput(id="near", name="Near", lat=45.05, lon=9.0, hours=hours(12.0))
    result = rank_spots(
        [far, near], CRUISING, origin=(45.0, 9.0), max_driving_km=50.0
    )
    assert [r.spot.id for r in result.results] == ["near"]
    assert len(result.excluded) == 1
    assert result.excluded[0].id == "far"
    assert "past your" in result.excluded[0].reason


def test_unknown_ramp_does_not_satisfy_a_hard_requirement():
    unknown = SpotInput(id="unknown", name="U", lat=None, lon=None, hours=hours(12.0))
    present = SpotInput(
        id="present", name="P", lat=None, lon=None, hours=hours(12.0), has_ramp=True
    )
    result = rank_spots([unknown, present], CRUISING, needs_ramp=True)
    assert [r.spot.id for r in result.results] == ["present"]
    assert "not assumed present" in result.excluded[0].reason


def test_spot_without_forecast_is_excluded_not_scored():
    empty = SpotInput(id="empty", name="E", lat=None, lon=None, hours=[])
    result = rank_spots([empty, spot("ok", 12.0)], CRUISING)
    assert [r.spot.id for r in result.results] == ["ok"]
    assert result.excluded[0].reason == "no forecast available"


def test_history_breaks_a_tie_between_identical_spots():
    plain = SpotInput(id="plain", name="Plain", lat=None, lon=None, hours=hours(12.0))
    loved = SpotInput(
        id="loved", name="Loved", lat=None, lon=None, hours=hours(12.0),
        rating_mean=9.5, rating_count=20,
    )
    result = rank_spots([plain, loved], CRUISING)
    assert [r.spot.id for r in result.results] == ["loved", "plain"]


def test_affinity_cannot_outweigh_conditions():
    """A beloved spot with no wind must not beat a good spot the user has never visited."""
    beloved_but_calm = SpotInput(
        id="beloved", name="Beloved", lat=None, lon=None, hours=hours(1.0),
        rating_mean=10.0, rating_count=100,
    )
    unknown_but_good = SpotInput(
        id="unknown", name="Unknown", lat=None, lon=None, hours=hours(12.0)
    )
    result = rank_spots([beloved_but_calm, unknown_but_good], CRUISING)
    assert [r.spot.id for r in result.results][0] == "unknown"


def test_limit_truncates_the_result():
    spots = [spot(f"s{i}", 10.0 + i) for i in range(5)]
    assert len(rank_spots(spots, CRUISING, limit=2).results) == 2


def test_ranking_is_deterministic():
    spots = [spot("a", 12.0), spot("b", 12.0), spot("c", 12.0)]
    first = [r.spot.id for r in rank_spots(spots, CRUISING).results]
    second = [r.spot.id for r in rank_spots(spots, CRUISING).results]
    assert first == second


def test_accessibility_data_improves_the_rank_score():
    bare = SpotInput(id="bare", name="Bare", lat=None, lon=None, hours=hours(12.0))
    equipped = SpotInput(
        id="equipped", name="Equipped", lat=None, lon=None, hours=hours(12.0),
        accessibility=AccessibilityInput(launch=1.0, parking=1.0, services=1.0),
    )
    result = rank_spots([bare, equipped], CRUISING)
    assert [r.spot.id for r in result.results] == ["equipped", "bare"]


def test_critical_warning_removes_the_recommendation_but_keeps_the_spot():
    stormy = SpotInput(
        id="stormy", name="Stormy", lat=None, lon=None,
        hours=[
            HourlyWeather(hour=9 + i, wind_kn=12.0, gust_kn=14.0, storm_prob=0.8)
            for i in range(6)
        ],
    )
    result = rank_spots([stormy], CRUISING)
    assert len(result.results) == 1  # still shown — the user decides
    assert result.results[0].recommended is False
    assert result.results[0].safety.has_critical


def test_explain_pair_names_the_deciding_components():
    result = rank_spots([spot("good", 12.0), spot("meh", 5.0)], CRUISING)
    deltas = explain_pair(result.results[0], result.results[1])
    assert deltas
    assert deltas[0]["component"] == "wind_quality"
    assert deltas[0]["delta_points"] > 0


def test_serialisation_shape_is_complete():
    result = rank_spots([spot("dervio", 12.0)], CRUISING)
    payload = result.as_dict()["results"][0]
    for key in (
        "spot", "sailing_score", "rank_score", "components", "wind",
        "best_window", "safety", "hourly", "recommended", "confidence",
    ):
        assert key in payload
    assert len(payload["hourly"]) == 8
    assert "disclaimer" in payload["safety"]
