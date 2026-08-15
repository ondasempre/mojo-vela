"""Open-Meteo adapter: normalisation and unit handling, verified offline.

**What this proves and what it does not.** The payload below is a hand-built sample
in the documented response shape, not a recorded live response — the environment
that wrote these tests had no network access. So these tests prove the *mapping* is
right: units, scaling, optional fields, thunderstorm derivation. They do **not**
prove the field names still match the live API.

That second guarantee needs a recorded payload in `data/contracts/open-meteo/` and a
scheduled job that checks the live schema (docs/09-testing-benchmarks.md, "Contract
tests"). Until someone runs the adapter against the real service once and records the
response, treat this as a mapping test only.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.adapters.weather_open_meteo import ATTRIBUTION, OpenMeteoProvider

SAMPLE = {
    "latitude": 46.08,
    "longitude": 9.31,
    "timezone": "Europe/Rome",
    "hourly": {
        "time": ["2026-08-15T09:00", "2026-08-15T10:00", "2026-08-15T11:00"],
        "wind_speed_10m": [5.0, 9.0, 14.0],
        "wind_gusts_10m": [7.0, 12.0, 18.0],
        "wind_direction_10m": [20.0, 180.0, 195.0],
        "temperature_2m": [21.0, 25.0, 28.0],
        "precipitation": [0.0, 0.0, 1.2],
        "precipitation_probability": [5, 10, 80],
        "cloud_cover": [20, 35, 90],
        "surface_pressure": [1013.0, 1012.0, 1010.0],
        "visibility": [24000.0, 20000.0, 8000.0],
        "weather_code": [0, 3, 95],
    },
}


@pytest.fixture
def provider():
    return OpenMeteoProvider(client=None)  # parse() needs no client


def test_wind_is_already_in_knots(provider):
    """The request asks for wind_speed_unit=kn, so no conversion must be applied."""
    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    assert [h.wind_kn for h in forecast.hours] == [5.0, 9.0, 14.0]
    assert [h.gust_kn for h in forecast.hours] == [7.0, 12.0, 18.0]


def test_percentages_become_fractions(provider):
    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    assert forecast.hours[2].precip_prob == pytest.approx(0.80)
    assert forecast.hours[2].cloud_frac == pytest.approx(0.90)
    assert all(0.0 <= h.precip_prob <= 1.0 for h in forecast.hours)
    assert all(0.0 <= h.cloud_frac <= 1.0 for h in forecast.hours)


def test_hours_are_parsed_from_the_timestamp(provider):
    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    assert [h.hour for h in forecast.hours] == [9, 10, 11]


def test_thunderstorm_code_becomes_a_flagged_probability(provider):
    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    assert forecast.hours[0].storm_prob == 0.0  # code 0, clear
    assert forecast.hours[1].storm_prob == 0.0  # code 3, overcast
    assert forecast.hours[2].storm_prob == 0.8  # code 95, thunderstorm
    assert any("WMO weather code" in n for n in forecast.notes)


def test_missing_visibility_stays_unknown(provider):
    payload = {**SAMPLE, "hourly": {**SAMPLE["hourly"], "visibility": [None, None, None]}}
    forecast = OpenMeteoProvider(client=None).parse(
        payload, spot_id="test", day=date(2026, 8, 15)
    )
    assert all(h.visibility_m is None for h in forecast.hours)
    assert any("does not publish visibility" in n for n in forecast.notes)


def test_absent_visibility_column_stays_unknown(provider):
    hourly = {k: v for k, v in SAMPLE["hourly"].items() if k != "visibility"}
    forecast = provider.parse({**SAMPLE, "hourly": hourly}, spot_id="t", day=date(2026, 8, 15))
    assert all(h.visibility_m is None for h in forecast.hours)


def test_attribution_travels_with_the_data(provider):
    """CC BY 4.0 requires it, so it is part of the payload, not a UI decoration."""
    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    assert forecast.attribution == ATTRIBUTION
    assert "Open-Meteo" in forecast.attribution
    assert forecast.provenance == "FORECAST"


def test_empty_response_is_an_error_not_an_empty_day(provider):
    with pytest.raises(ValueError):
        provider.parse({"hourly": {"time": []}}, spot_id="test", day=date(2026, 8, 15))


def test_scoring_the_parsed_forecast_end_to_end(provider):
    """The adapter's output must be directly consumable by the engine."""
    from sailwise_ref.profiles import ProfileId, get_profile
    from sailwise_ref.safety import evaluate_safety
    from sailwise_ref.score import sailing_score

    forecast = provider.parse(SAMPLE, spot_id="test", day=date(2026, 8, 15))
    result = sailing_score(forecast.hours, get_profile(ProfileId.CRUISING))
    assert 0 <= result.total <= 100

    report = evaluate_safety(forecast.hours, get_profile(ProfileId.CRUISING))
    # Code 95 at 11:00 is a thunderstorm: 0.8 is above the CRITICAL threshold.
    assert report.has_critical
