"""API tests. Fixture provider, no network, deterministic."""

from __future__ import annotations

import re


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["weather_provider"] == "fixture"
    assert body["spots"]["total"] == 3
    assert body["spots"]["resolved"] == 3
    assert "not a safety clearance" in body["disclaimer"]


def test_spots_listing_carries_state_and_attribution(client):
    body = client.get("/api/spots").json()
    spots = body["data"]["spots"]
    assert len(spots) == 3
    assert {s["state"] for s in spots} == {"ingested"}
    assert "OpenStreetMap" in body["meta"]["attribution"]


def test_recommendations_return_ranked_spots(client):
    body = client.post("/api/recommendations", json={"profile": "CRUISING"}).json()
    results = body["data"]["results"]
    assert results
    scores = [r["rank_score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    first = results[0]
    for key in ("sailing_score", "components", "wind", "safety", "hourly", "best_window"):
        assert key in first
    assert 0 <= first["sailing_score"] <= 100


def test_every_response_carries_provenance_and_the_disclaimer(client):
    meta = client.post("/api/recommendations", json={"profile": "RELAX"}).json()["meta"]
    assert "not a safety clearance" in meta["disclaimer"]
    assert meta["sources"]
    assert meta["sources"][0]["provenance"] == "SYNTHETIC"
    assert meta["demo_mode"] is True


def test_demo_mode_is_flagged_so_synthetic_data_cannot_pass_as_real(client):
    body = client.post("/api/recommendations", json={"profile": "CRUISING"}).json()
    assert body["meta"]["demo_mode"] is True
    note = " ".join(body["meta"]["sources"][0]["notes"])
    assert "SYNTHETIC" in note


def test_profiles_disagree_about_the_same_day(client):
    family = client.post("/api/recommendations", json={"profile": "FAMILY"}).json()
    sport = client.post("/api/recommendations", json={"profile": "SPORT"}).json()
    family_scores = {r["spot"]["id"]: r["sailing_score"] for r in family["data"]["results"]}
    sport_scores = {r["spot"]["id"]: r["sailing_score"] for r in sport["data"]["results"]}
    assert family_scores != sport_scores


def test_driving_limit_excludes_with_a_reason(client):
    body = client.post(
        "/api/recommendations",
        json={
            "profile": "CRUISING",
            "origin_lat": 46.0,
            "origin_lon": 9.0,
            "max_driving_km": 30,
        },
    ).json()
    ids = {r["spot"]["id"] for r in body["data"]["results"]}
    assert "charlie" not in ids  # ~200 km away
    excluded = {e["id"]: e["reason"] for e in body["data"]["excluded"]}
    assert "charlie" in excluded
    assert "past your" in excluded["charlie"]


def test_distance_is_labelled_as_an_estimate(client):
    body = client.post(
        "/api/recommendations",
        json={"profile": "CRUISING", "origin_lat": 46.0, "origin_lon": 9.0, "max_driving_km": 500},
    ).json()
    distances = [r["distance"] for r in body["data"]["results"] if r["distance"]]
    assert distances
    assert all(d["provenance"] == "ESTIMATED" for d in distances)


def test_needs_ramp_filters_on_known_data_only(client):
    body = client.post(
        "/api/recommendations", json={"profile": "CRUISING", "needs_ramp": True}
    ).json()
    ids = {r["spot"]["id"] for r in body["data"]["results"]}
    assert ids == {"alpha"}  # the only spot with a recorded ramp
    reasons = {e["reason"] for e in body["data"]["excluded"]}
    assert any("unknown" in r for r in reasons)


def test_unknown_accessibility_is_reported_as_unknown_not_zero(client):
    body = client.post("/api/recommendations", json={"profile": "CRUISING"}).json()
    bravo = next(r for r in body["data"]["results"] if r["spot"]["id"] == "bravo")
    access = next(c for c in bravo["components"] if c["id"] == "accessibility")
    assert access["known"] is False
    assert access["raw"] is None
    assert bravo["confidence"] < 1.0


def test_plan_for_one_spot(client):
    body = client.get("/api/spots/alpha/plan?profile=CRUISING").json()
    assert body["data"]["spot"]["id"] == "alpha"
    assert body["data"]["hourly"]
    assert "disclaimer" in body["meta"]


def test_unknown_spot_is_404(client):
    assert client.get("/api/spots/nowhere/plan").status_code == 404


def test_invalid_time_range_is_rejected(client):
    response = client.post(
        "/api/recommendations",
        json={"profile": "CRUISING", "earliest_hour": 18, "latest_hour": 9},
    )
    assert response.status_code == 422


def test_cache_is_used_on_the_second_identical_request(client):
    client.post("/api/recommendations", json={"profile": "CRUISING"})
    second = client.post("/api/recommendations", json={"profile": "CRUISING"}).json()
    assert second["meta"]["cache"]["hits"] > 0
    assert second["meta"]["sources"][0]["cache"]["state"] == "HIT"


def test_cache_can_be_invalidated(client):
    client.post("/api/recommendations", json={"profile": "CRUISING"})
    removed = client.post("/api/cache/invalidate").json()["data"]["removed"]
    assert removed > 0


def test_profiles_endpoint_exposes_the_weights(client):
    profiles = client.get("/api/profiles").json()["data"]
    assert len(profiles) == 6
    cruising = next(p for p in profiles if p["id"] == "CRUISING")
    assert cruising["weights"]["wind_quality"] == 0.30
    assert cruising["wind_band_kn"] == [4.0, 8.0, 16.0, 22.0]


def test_ui_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SailWise" in response.text


def test_static_assets_are_served_with_a_content_hash(client):
    """A stylesheet edit must reach the browser.

    Without this the browser keeps the old CSS and styles the new markup with it,
    which is how the form ended up with its unit labels dangling below the inputs
    long after the CSS had been fixed.
    """
    html = client.get("/").text
    urls = re.findall(r'/static/(styles\.css|app\.js)\?v=([0-9a-f]{10})', html)
    assert {name for name, _ in urls} == {"styles.css", "app.js"}
    for name, digest in urls:
        assert client.get(f"/static/{name}?v={digest}").status_code == 200
