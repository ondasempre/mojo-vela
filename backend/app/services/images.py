"""Photographs of boats sailing, shown in the hero band and the spot gallery.

Photographs have authors. That is the whole design constraint here, and it is why
this looks like the webcam and event modules rather than like a folder of files:

* every image carries a **credit** and a **licence**, and both are rendered;
* an entry whose file is missing from disk is dropped rather than shown broken;
* nothing ships in the repository except the built-in SVG illustrations, which were
  drawn for this project and carry no third-party rights.

Add your own photos — the ones you took — and they appear immediately. Putting
someone else's photograph in here because it looks good is exactly the thing this
module is arranged to make you think about first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

#: Built-in vector illustrations, always available, drawn for this project.
BUILTIN_LIGHT = "/static/img/hero-light.svg"
BUILTIN_DARK = "/static/img/hero-dark.svg"

ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg"})


@dataclass(frozen=True)
class Photo:
    id: str
    url: str
    caption: str | None
    credit: str | None
    licence: str | None
    source_url: str | None
    water_body: str | None
    spot_id: str | None
    #: True for the built-in illustrations, so the UI can label them as drawings.
    builtin: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "caption": self.caption,
            "credit": self.credit,
            "licence": self.licence,
            "source_url": self.source_url,
            "water_body": self.water_body,
            "spot_id": self.spot_id,
            "builtin": self.builtin,
        }


BUILTIN_PHOTOS = [
    Photo(
        id="builtin-light",
        url=BUILTIN_LIGHT,
        caption="Barca a vela su un lago alpino",
        credit="Illustrazione SailWise",
        licence="MIT (parte di questo progetto)",
        source_url=None,
        water_body=None,
        spot_id=None,
        builtin=True,
    ),
    Photo(
        id="builtin-dark",
        url=BUILTIN_DARK,
        caption="Barca a vela al tramonto",
        credit="Illustrazione SailWise",
        licence="MIT (parte di questo progetto)",
        source_url=None,
        water_body=None,
        spot_id=None,
        builtin=True,
    ),
]


class ImageService:
    def __init__(self, data_dir: Path, dataset: str = "images") -> None:
        self._dir = data_dir / "images"
        self._path = self._dir / f"{dataset}.json"
        self._photos: list[Photo] = []
        self._problems: list[str] = []
        self._load()

    @property
    def photos_dir(self) -> Path:
        return self._dir / "photos"

    @property
    def problems(self) -> list[str]:
        return self._problems

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._problems.append(f"{self._path.name}: {exc}")
            return

        for index, entry in enumerate(payload.get("photos", [])):
            photo = self._build(entry, index)
            if photo is not None:
                self._photos.append(photo)

    def _build(self, entry: dict, index: int) -> Photo | None:
        url = entry.get("url")
        filename = entry.get("file")

        if filename:
            # Local files only, and only from inside the photos directory: a manifest
            # is data, and data must not be able to reach into the filesystem.
            candidate = (self.photos_dir / filename).resolve()
            try:
                candidate.relative_to(self.photos_dir.resolve())
            except ValueError:
                self._problems.append(f"'{filename}' esce dalla cartella photos/: ignorato")
                return None
            if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
                self._problems.append(f"'{filename}': estensione non supportata")
                return None
            if not candidate.is_file():
                self._problems.append(f"'{filename}' è nel manifest ma non sul disco")
                return None
            url = f"/photos/{filename}"

        if not url:
            self._problems.append(f"voce #{index + 1}: manca sia 'file' sia 'url'")
            return None

        if not entry.get("credit"):
            # A photograph without an author is a photograph you cannot publish.
            self._problems.append(f"'{filename or url}': manca il credito, voce ignorata")
            return None

        return Photo(
            id=str(entry.get("id") or filename or url),
            url=url,
            caption=entry.get("caption"),
            credit=entry.get("credit"),
            licence=entry.get("licence"),
            source_url=entry.get("source_url"),
            water_body=entry.get("water_body"),
            spot_id=entry.get("spot_id"),
        )

    # --- queries ----------------------------------------------------------

    def gallery(self, water_body: str | None = None, spot_id: str | None = None) -> list[Photo]:
        """Most specific first: this spot, then this lake, then anything else."""
        if not self._photos:
            return []

        def rank(photo: Photo) -> int:
            if spot_id and photo.spot_id == spot_id:
                return 0
            if water_body and photo.water_body == water_body:
                return 1
            if photo.spot_id is None and photo.water_body is None:
                return 2
            return 3

        ranked = sorted(self._photos, key=rank)
        return [p for p in ranked if rank(p) < 3] or ranked

    def hero(self, water_body: str | None = None, spot_id: str | None = None) -> Photo:
        """One image for the banner, stable for the day so it does not flicker.

        Falls back to the built-in illustration, which is why the app never looks
        empty and never needs a placeholder photograph of someone else's boat.
        """
        candidates = self.gallery(water_body, spot_id)
        if not candidates:
            return BUILTIN_PHOTOS[0]
        return candidates[date.today().toordinal() % len(candidates)]

    def as_dict(self, water_body: str | None = None, spot_id: str | None = None) -> dict:
        gallery = self.gallery(water_body, spot_id)
        return {
            "hero": self.hero(water_body, spot_id).as_dict(),
            "gallery": [p.as_dict() for p in gallery],
            "builtin": {"light": BUILTIN_LIGHT, "dark": BUILTIN_DARK},
            "count": len(gallery),
            "problems": self._problems,
        }
