"""Test fixtures for the backend.

Every test runs against the **fixture weather provider** with geocoding disabled.
No test in this repository touches a live service: tests must be deterministic,
offline, and free of anyone's rate limit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

#: Coordinates used only inside tests. They are round, obviously-synthetic numbers,
#: and they never leave the temporary directory a test creates. Real spot data is
#: sourced through scripts/fetch_spots.py, never written by hand.
TEST_SPOTS = [
    {"id": "alpha", "name": "Alpha", "lat": 46.0, "lon": 9.0},
    {"id": "bravo", "name": "Bravo", "lat": 46.1, "lon": 9.1},
    {"id": "charlie", "name": "Charlie", "lat": 47.5, "lon": 10.5},
]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    spots = tmp_path / "spots"
    spots.mkdir(parents=True)

    seed = {
        "dataset": "test_lakes",
        "water_bodies": [
            {
                "id": "test_lake",
                "name": "Test Lake",
                "type": "LAKE",
                "timezone": "Europe/Rome",
            }
        ],
        "spots": [
            {
                "id": s["id"],
                "name": s["name"],
                "water_body": "test_lake",
                "query": s["name"],
                "priority": 1,
            }
            for s in TEST_SPOTS
        ],
    }
    (spots / "test_lakes.seed.json").write_text(json.dumps(seed), encoding="utf-8")

    ingested = {
        "dataset": "test_lakes",
        "spots": [
            {
                **s,
                "source": "test",
                "retrieved_at": "2026-08-15T00:00:00Z",
                "facilities": {"launch_point": [{"name": "ramp", "source": "test"}]}
                if s["id"] == "alpha"
                else {},
            }
            for s in TEST_SPOTS
        ],
    }
    (spots / "test_lakes.json").write_text(json.dumps(ingested), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(data_dir: Path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAILWISE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SAILWISE_SPOTS_DATASET", "test_lakes")
    monkeypatch.setenv("SAILWISE_WEATHER_PROVIDER", "fixture")
    monkeypatch.setenv("SAILWISE_GEOCODING", "0")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
