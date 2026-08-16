"""Tests for the guides.

Editorial content still has rules, and these are them: a claim about a specific
lake carries a source, a section with nothing sourced says so rather than being
quietly filled, and the safety page keeps its disclaimer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.knowledge import TOPICS, KnowledgeService

REPO_DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def service():
    return KnowledgeService(REPO_DATA)


def test_all_topics_load_without_problems(service):
    assert service.problems == []
    assert {t["topic"] for t in service.available()} == set(TOPICS)


def test_every_topic_has_a_title_and_an_intro(service):
    for topic in TOPICS:
        payload = service.get(topic)
        assert payload["title"]
        assert payload["intro"]
        assert payload["emoji"]


def test_unknown_topic_returns_none(service):
    assert service.get("nonexistent") is None


# --- winds -----------------------------------------------------------------


def test_every_wind_card_cites_a_source(service):
    """A claim about when a specific wind blows is a local claim, not general knowledge."""
    for lake in service.get("winds")["lakes"]:
        for wind in lake["winds"]:
            assert wind["source"].startswith("http"), f"{wind['name']} has no source"


def test_every_wind_card_is_complete(service):
    required = {"name", "type", "direction", "hours", "strength", "sailing"}
    for lake in service.get("winds")["lakes"]:
        for wind in lake["winds"]:
            assert required <= set(wind), f"{wind['name']} is missing {required - set(wind)}"


def test_a_lake_without_sourced_winds_says_so_instead_of_inventing(service):
    """Lake Iseo has no sourced description. That must read as an absence, not a gap."""
    iseo = service.winds_for_lake("lago_iseo")
    assert iseo is not None
    assert iseo["winds"] == []
    assert iseo["unknown_note"]
    assert "data/knowledge" in iseo["unknown_note"]


def test_winds_carry_the_not_a_forecast_caveat(service):
    winds = service.get("winds")
    assert "indicativi" in winds["caveat"]
    assert "previsione" in winds["caveat"]


def test_winds_for_lake_matches_the_spot_dataset_ids():
    """The wind guide keys on the same water body ids as the spot dataset."""
    seed = json.loads(
        (REPO_DATA / "spots" / "italian_lakes.seed.json").read_text(encoding="utf-8")
    )
    dataset_ids = {b["id"] for b in seed["water_bodies"]}
    service = KnowledgeService(REPO_DATA)
    guide_ids = {lake["id"] for lake in service.get("winds")["lakes"]}
    unknown = guide_ids - dataset_ids
    assert not unknown, f"guide has lakes the dataset does not know: {unknown}"


# --- knots -----------------------------------------------------------------


def test_every_knot_has_a_diagram_that_exists():
    static = Path(__file__).resolve().parents[1] / "static"
    service = KnowledgeService(REPO_DATA)
    for knot in service.get("knots")["knots"]:
        path = static / knot["image"].removeprefix("/static/")
        assert path.is_file(), f"missing diagram for {knot['name']}: {path}"


def test_every_knot_explains_when_not_to_use_it(service):
    """The warning is the part that keeps someone out of trouble."""
    for knot in service.get("knots")["knots"]:
        assert knot["warning"]
        assert knot["steps"]
        assert knot["use"]


def test_the_reef_knot_warns_against_joining_two_lines(service):
    """The single most dangerous misuse of a knot in this list."""
    reef = next(k for k in service.get("knots")["knots"] if k["id"] == "piano")
    assert "giunzione" in reef["warning"]


# --- mooring and safety ----------------------------------------------------


def test_mooring_types_are_complete(service):
    required = {"title", "when", "steps", "lines", "tip", "difficulty"}
    for entry in service.get("mooring")["types"]:
        assert required <= set(entry), f"{entry['title']} is missing {required - set(entry)}"


def test_safety_keeps_its_disclaimer(service):
    safety = service.get("safety")
    assert "non un via libera alla sicurezza" in safety["disclaimer"]
    assert "112" in json.dumps(safety, ensure_ascii=False)


def test_safety_does_not_claim_to_be_a_regulation(service):
    caveat = service.get("safety")["caveat"]
    assert "non un corso di sicurezza" in caveat
    assert "non una fonte normativa" in caveat


# --- API -------------------------------------------------------------------


def test_knowledge_index_endpoint(client):
    body = client.get("/api/knowledge").json()
    assert {t["topic"] for t in body["data"]["topics"]} == set(TOPICS)


def test_knowledge_topic_endpoint(client):
    body = client.get("/api/knowledge/knots").json()
    assert len(body["data"]["knots"]) == 5


def test_unknown_topic_is_404(client):
    assert client.get("/api/knowledge/nope").status_code == 404


def test_knot_diagrams_are_served(client):
    for name in ("bowline", "reef", "clove", "figure8", "cleat"):
        response = client.get(f"/static/img/knots/{name}.svg")
        assert response.status_code == 200
        assert "<svg" in response.text
