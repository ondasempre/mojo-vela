"""Tests for the photo manifest.

The rules encoded here are the ones that keep the project out of trouble: a
photograph without a credit is not shown, a manifest entry cannot reach outside the
photos directory, and there is always a built-in illustration to fall back on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.images import BUILTIN_DARK, BUILTIN_LIGHT, ImageService


def write_manifest(root: Path, photos: list[dict]) -> None:
    images = root / "images"
    (images / "photos").mkdir(parents=True, exist_ok=True)
    (images / "images.json").write_text(json.dumps({"photos": photos}), encoding="utf-8")


def touch_photo(root: Path, name: str) -> None:
    (root / "images" / "photos" / name).write_bytes(b"\xff\xd8\xff")  # a JPEG-ish stub


def test_missing_manifest_falls_back_to_the_builtin_illustration(tmp_path):
    service = ImageService(tmp_path)
    assert service.gallery() == []
    hero = service.hero()
    assert hero.builtin is True
    assert hero.url == BUILTIN_LIGHT


def test_builtin_urls_are_exposed_for_both_themes(tmp_path):
    payload = ImageService(tmp_path).as_dict()
    assert payload["builtin"]["light"] == BUILTIN_LIGHT
    assert payload["builtin"]["dark"] == BUILTIN_DARK


def test_a_photo_without_credit_is_dropped(tmp_path):
    """A photograph you cannot attribute is a photograph you cannot publish."""
    write_manifest(tmp_path, [{"id": "x", "file": "a.jpg", "caption": "Bella"}])
    touch_photo(tmp_path, "a.jpg")
    service = ImageService(tmp_path)
    assert service.gallery() == []
    assert any("credito" in p for p in service.problems)


def test_a_photo_listed_but_absent_from_disk_is_dropped(tmp_path):
    write_manifest(tmp_path, [{"id": "x", "file": "missing.jpg", "credit": "Someone"}])
    service = ImageService(tmp_path)
    assert service.gallery() == []
    assert any("non sul disco" in p for p in service.problems)


@pytest.mark.parametrize("escape", ["../secret.jpg", "../../etc/passwd.jpg", "sub/../../out.jpg"])
def test_a_manifest_cannot_reach_outside_the_photos_directory(tmp_path, escape):
    """The manifest is data. Data must not be able to address the filesystem."""
    write_manifest(tmp_path, [{"id": "x", "file": escape, "credit": "Someone"}])
    service = ImageService(tmp_path)
    assert service.gallery() == []


def test_unsupported_extensions_are_rejected(tmp_path):
    write_manifest(tmp_path, [{"id": "x", "file": "a.exe", "credit": "Someone"}])
    touch_photo(tmp_path, "a.exe")
    service = ImageService(tmp_path)
    assert service.gallery() == []
    assert any("estensione" in p for p in service.problems)


def test_a_valid_photo_is_served_from_the_photos_route(tmp_path):
    write_manifest(
        tmp_path,
        [{"id": "dervio", "file": "dervio.jpg", "credit": "Flavio", "licence": "CC BY 4.0",
          "water_body": "lago_di_como", "caption": "Breva"}],
    )
    touch_photo(tmp_path, "dervio.jpg")
    photos = ImageService(tmp_path).gallery()
    assert len(photos) == 1
    assert photos[0].url == "/photos/dervio.jpg"
    assert photos[0].credit == "Flavio"
    assert photos[0].as_dict()["licence"] == "CC BY 4.0"


def test_remote_urls_are_allowed_when_credited(tmp_path):
    write_manifest(tmp_path, [{"id": "r", "url": "https://example.org/a.jpg", "credit": "Someone"}])
    photos = ImageService(tmp_path).gallery()
    assert [p.url for p in photos] == ["https://example.org/a.jpg"]


def test_gallery_prefers_the_spot_then_the_lake(tmp_path):
    write_manifest(
        tmp_path,
        [
            {"id": "generic", "url": "https://example.org/g.jpg", "credit": "A"},
            {"id": "lake", "url": "https://example.org/l.jpg", "credit": "B",
             "water_body": "lago_di_como"},
            {"id": "spot", "url": "https://example.org/s.jpg", "credit": "C",
             "water_body": "lago_di_como", "spot_id": "dervio"},
        ],
    )
    service = ImageService(tmp_path)
    order = [p.id for p in service.gallery("lago_di_como", "dervio")]
    assert order[0] == "spot"
    assert order[1] == "lake"


def test_hero_is_stable_within_a_day(tmp_path):
    write_manifest(
        tmp_path,
        [{"id": f"p{i}", "url": f"https://example.org/{i}.jpg", "credit": "A"} for i in range(5)],
    )
    service = ImageService(tmp_path)
    assert service.hero().id == service.hero().id


def test_photos_route_rejects_traversal(client):
    assert client.get("/photos/../../etc/passwd").status_code in (404, 400)


def test_builtin_svgs_are_served(client):
    for url in (BUILTIN_LIGHT, BUILTIN_DARK):
        response = client.get(url)
        assert response.status_code == 200
        assert "svg" in response.text[:200].lower()


def test_images_endpoint_reports_the_fallback(client):
    body = client.get("/api/images").json()
    assert body["data"]["hero"]["builtin"] is True
    assert body["data"]["count"] == 0
    assert "data/images" in body["meta"]["note"]
