"""Tests for POI parsing, parking assessment, webcams and events.

All offline. The Overpass and Windy payloads below are hand-built in the documented
response shape, not recorded live responses — same caveat as the Open-Meteo adapter:
they prove the mapping, not that the upstream schema still matches.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.adapters.events import (
    CuratedEventsProvider,
    IcsEventsProvider,
    merge_events,
)
from app.adapters.poi_overpass import OverpassPoiProvider, classify, haversine_m
from app.adapters.webcams import CuratedWebcamProvider
from app.services.places import PlacesService

SPOT_LAT, SPOT_LON = 46.0, 9.0

OVERPASS_SAMPLE = {
    "elements": [
        {
            "type": "node", "id": 1, "lat": 46.0009, "lon": 9.0,
            "tags": {"amenity": "parking", "name": "Parcheggio lago", "fee": "no",
                     "capacity": "40"},
        },
        {
            "type": "node", "id": 2, "lat": 46.002, "lon": 9.0,
            "tags": {"amenity": "motorcycle_parking", "capacity": "12", "covered": "yes"},
        },
        {
            "type": "way", "id": 3, "center": {"lat": 46.0005, "lon": 9.0005},
            "tags": {"leisure": "slipway", "name": "Scivolo comunale"},
        },
        {
            "type": "node", "id": 4, "lat": 46.001, "lon": 9.001,
            "tags": {"amenity": "restaurant", "name": "Osteria del Vento", "cuisine": "italian",
                     "opening_hours": "Tu-Su 12:00-22:00", "phone": "+39 000",
                     "website": "https://example.org"},
        },
        {"type": "node", "id": 5, "lat": 46.003, "lon": 9.0,
         "tags": {"tourism": "picnic_site", "name": "Area picnic"}},
        {"type": "node", "id": 6, "lat": 46.004, "lon": 9.0,
         "tags": {"club": "sailing", "name": "Circolo Vela Esempio", "website": "https://example.org/cv"}},
        {"type": "node", "id": 7, "lat": 46.005, "lon": 9.0, "tags": {"amenity": "bench"}},
        {"type": "way", "id": 8, "tags": {"amenity": "parking"}},  # no centre → skipped
    ]
}


@pytest.fixture
def parsed():
    return OverpassPoiProvider(client=None, user_agent="test").parse(
        OVERPASS_SAMPLE, SPOT_LAT, SPOT_LON
    )


# --- classification --------------------------------------------------------


def test_classify_covers_the_categories_we_promise():
    assert classify({"amenity": "parking"}) == "parking"
    assert classify({"amenity": "motorcycle_parking"}) == "motorcycle_parking"
    assert classify({"amenity": "restaurant"}) == "restaurant"
    assert classify({"amenity": "pub"}) == "bar"
    assert classify({"amenity": "ice_cream"}) == "ice_cream"
    assert classify({"tourism": "picnic_site"}) == "picnic"
    assert classify({"leisure": "picnic_table"}) == "picnic"
    assert classify({"club": "sailing"}) == "sailing_club"
    assert classify({"leisure": "slipway"}) == "slipway"
    assert classify({"shop": "boat"}) == "boat_service"
    assert classify({"amenity": "bench"}) is None


def test_car_and_motorcycle_parking_are_different_categories():
    """A sailor on a bike needs a different answer from one with a trailer."""
    grouped = OverpassPoiProvider(client=None, user_agent="t").parse(
        OVERPASS_SAMPLE, SPOT_LAT, SPOT_LON
    ).by_category()
    assert len(grouped["parking"]) == 1
    assert len(grouped["motorcycle_parking"]) == 1


# --- parsing ---------------------------------------------------------------


def test_elements_without_a_position_are_dropped(parsed):
    """A way with no resolved centre has no distance, so it is not an entry."""
    assert all(p.osm_id != 8 for p in parsed.places)


def test_untagged_elements_are_ignored(parsed):
    assert all(p.osm_id != 7 for p in parsed.places)


def test_places_are_sorted_by_distance(parsed):
    distances = [p.distance_m for p in parsed.places]
    assert distances == sorted(distances)


def test_way_centre_is_used_for_distance(parsed):
    slipway = next(p for p in parsed.places if p.osm_id == 3)
    assert slipway.category == "slipway"
    assert slipway.distance_m > 0


def test_links_are_built_from_coordinates(parsed):
    place = next(p for p in parsed.places if p.osm_id == 4)
    payload = place.as_dict()
    assert payload["maps_url"].startswith("https://www.google.com/maps/search/")
    assert f"{place.lat:.6f}" in payload["maps_url"]
    assert payload["directions_url"].startswith("https://www.google.com/maps/dir/")
    assert payload["osm_url"] == "https://www.openstreetmap.org/node/4"
    assert payload["website"] == "https://example.org"
    assert payload["phone"] == "+39 000"
    assert payload["emoji"] == "🍝"


def test_walking_time_is_derived_from_distance(parsed):
    payload = next(p for p in parsed.places if p.osm_id == 6).as_dict()
    assert payload["walk_min"] >= 1


def test_attribution_is_always_present(parsed):
    assert "OpenStreetMap" in parsed.attribution


def test_haversine_sanity():
    assert haversine_m(46.0, 9.0, 46.0, 9.0) == 0.0
    assert 100 < haversine_m(46.0, 9.0, 46.001, 9.0) < 120


# --- parking assessment ----------------------------------------------------


@pytest.fixture
def service(tmp_path: Path):
    from app.adapters.cache_memory import MemoryCache

    return PlacesService(
        poi=OverpassPoiProvider(client=None, user_agent="t"),
        cache=MemoryCache(),
        curated_webcams=CuratedWebcamProvider(tmp_path),
        curated_events=CuratedEventsProvider(tmp_path),
    )


def test_parking_assessment_explains_itself(service, parsed):
    assessment = service.assess_parking(parsed)
    assert assessment.score is not None
    assert 0.0 <= assessment.score <= 1.0
    assert assessment.nearest_m is not None
    assert assessment.free is True  # fee=no
    assert any("m dal punto di partenza" in r for r in assessment.reasons)


def test_motorcycle_parking_is_assessed_separately(service, parsed):
    car = service.assess_parking(parsed)
    moto = service.assess_parking(parsed, motorcycle=True)
    assert car.nearest_m != moto.nearest_m


def test_missing_parking_is_unknown_not_zero(service):
    empty = OverpassPoiProvider(client=None, user_agent="t").parse({"elements": []}, 46.0, 9.0)
    assessment = service.assess_parking(empty)
    assert assessment.score is None
    assert assessment.free is None
    assert "nessun parcheggio mappato" in assessment.reasons[0]


def test_unknown_fee_is_neither_rewarded_nor_punished(service):
    payload = {"elements": [
        {"type": "node", "id": 1, "lat": 46.0005, "lon": 9.0, "tags": {"amenity": "parking"}}
    ]}
    parsed_local = OverpassPoiProvider(client=None, user_agent="t").parse(payload, 46.0, 9.0)
    assessment = service.assess_parking(parsed_local)
    assert assessment.free is None
    assert any("non sappiamo" in r for r in assessment.reasons)


def test_accessibility_uses_real_data_but_never_invents_a_ramp(service, parsed):
    access = service.accessibility_from(parsed)
    assert access.launch == 1.0  # a slipway is mapped
    assert access.parking is not None

    no_launch = OverpassPoiProvider(client=None, user_agent="t").parse(
        {"elements": [{"type": "node", "id": 1, "lat": 46.0005, "lon": 9.0,
                       "tags": {"amenity": "parking"}}]}, 46.0, 9.0
    )
    # No slipway mapped is not evidence there is no ramp (FR-P-03).
    assert service.accessibility_from(no_launch).launch is None


def test_sections_are_ordered_and_labelled(service, parsed):
    sections = service.sections_from(parsed)
    ids = [s["id"] for s in sections]
    assert ids == ["launch", "parking_car", "parking_moto", "food", "picnic", "clubs", "services"]
    assert all(s["emoji"] for s in sections)
    food = next(s for s in sections if s["id"] == "food")
    assert food["count"] == 1


# --- webcams ---------------------------------------------------------------


def test_curated_webcams_missing_file_is_empty_not_an_error(tmp_path):
    provider = CuratedWebcamProvider(tmp_path)
    assert provider.by_water_body("lago_di_como") == []


@pytest.mark.asyncio
async def test_curated_webcam_without_url_is_skipped(tmp_path):
    (tmp_path / "webcams").mkdir()
    (tmp_path / "webcams" / "webcams.json").write_text(
        '{"webcams": ['
        '{"id": "a", "title": "Buona", "url": "https://example.org/a", "lat": 46.0, "lon": 9.0},'
        '{"id": "b", "title": "Senza link", "lat": 46.0, "lon": 9.0}]}',
        encoding="utf-8",
    )
    found = await CuratedWebcamProvider(tmp_path).near(46.0, 9.0)
    assert [w.id for w in found] == ["a"]


@pytest.mark.asyncio
async def test_distant_webcams_are_excluded(tmp_path):
    (tmp_path / "webcams").mkdir()
    (tmp_path / "webcams" / "webcams.json").write_text(
        '{"webcams": [{"id": "far", "title": "Lontana", "url": "https://example.org",'
        ' "lat": 47.5, "lon": 10.5}]}',
        encoding="utf-8",
    )
    assert await CuratedWebcamProvider(tmp_path).near(46.0, 9.0, radius_km=15) == []


# --- events ----------------------------------------------------------------


def test_curated_events_filter_by_lake_and_drop_past_ones(tmp_path):
    (tmp_path / "events").mkdir()
    (tmp_path / "events" / "events.json").write_text(
        '{"events": ['
        '{"id": "1", "title": "Regata futura", "start": "2026-09-12", "water_body": "como",'
        ' "category": "regatta"},'
        '{"id": "2", "title": "Regata passata", "start": "2026-01-01", "water_body": "como"},'
        '{"id": "3", "title": "Altro lago", "start": "2026-09-12", "water_body": "garda"}'
        '], "ics_feeds": []}',
        encoding="utf-8",
    )
    provider = CuratedEventsProvider(tmp_path)
    events = provider.upcoming("como", today=date(2026, 8, 15))
    assert [e.id for e in events] == ["1"]
    assert events[0].as_dict()["emoji"] == "🏁"


ICS_SAMPLE = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:evt-1
SUMMARY:Trofeo di primavera - regata sociale
DTSTART;VALUE=DATE:20260912
DTEND;VALUE=DATE:20260913
LOCATION:Dervio
URL:https://example.org/bando
END:VEVENT
BEGIN:VEVENT
UID:evt-2
SUMMARY:Corso di vela per pri
 ncipianti
DTSTART:20260920T090000Z
END:VEVENT
END:VCALENDAR
"""


def test_ics_parser_reads_events_and_categorises_them():
    events = IcsEventsProvider(client=None).parse(ICS_SAMPLE, source_url="https://example.org/c.ics")
    assert len(events) == 2
    assert events[0].start == "2026-09-12"
    assert events[0].end == "2026-09-13"
    assert events[0].category == "regatta"
    assert events[0].location == "Dervio"
    assert events[0].url == "https://example.org/bando"


def test_ics_parser_unfolds_wrapped_lines():
    """RFC 5545 folding: a continuation line starts with a space. Miss it and titles break."""
    events = IcsEventsProvider(client=None).parse(ICS_SAMPLE)
    assert events[1].title == "Corso di vela per principianti"
    assert events[1].category == "course"
    assert events[1].start == "2026-09-20T09:00:00"


def test_ics_without_summary_or_start_is_skipped():
    text = "BEGIN:VEVENT\nUID:x\nDTSTART:20260101\nEND:VEVENT"
    assert IcsEventsProvider(client=None).parse(text) == []


def test_merge_drops_duplicates_across_sources():
    events = IcsEventsProvider(client=None).parse(ICS_SAMPLE)
    merged = merge_events([events, events])
    assert len(merged) == 2
