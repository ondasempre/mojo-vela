"""Sailing events near a lake: regattas, courses, club meetings.

Why this looks the way it does. The obvious model is "scrape a sailing news site" —
veleitaliane.it and similar. That is not available to us: a web page is not an API,
and using one against its terms is out of scope permanently (docs, rule 29). There is
also no open, national calendar API for Italian sailing.

So events come from two routes that are both legitimate and both testable offline:

1. **A curated dataset** (`data/events/<dataset>.json`) — entries added by hand or by
   a club, each with a source URL and the date it was checked.
2. **ICS calendar feeds** — many clubs and federations publish a calendar. Subscribing
   to a feed the club publishes for that purpose is exactly what it is for, and the
   parser below is deliberately small: enough for VEVENT summaries and dates, nothing
   more.

An empty events list is a real answer. It means "we have no verified events", which is
different from "there are none", and the UI says so in those words.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx


@dataclass(frozen=True)
class SailingEvent:
    id: str
    title: str
    start: str  # ISO date or datetime
    end: str | None = None
    location: str | None = None
    water_body: str | None = None
    organiser: str | None = None
    category: str = "event"  # regatta | course | social | event
    url: str | None = None
    description: str | None = None
    source: str = "curated"
    source_url: str | None = None
    checked_at: str | None = None

    @property
    def start_date(self) -> date | None:
        try:
            return date.fromisoformat(self.start[:10])
        except (ValueError, IndexError):
            return None

    def as_dict(self) -> dict:
        emoji = {
            "regatta": "🏁",
            "course": "🎓",
            "social": "🎉",
            "event": "📅",
        }.get(self.category, "📅")
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "location": self.location,
            "water_body": self.water_body,
            "organiser": self.organiser,
            "category": self.category,
            "emoji": emoji,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "source_url": self.source_url,
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class EventsResult:
    events: list[SailingEvent]
    sources: list[str]
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "events": [e.as_dict() for e in self.events],
            "sources": self.sources,
            "note": self.note,
        }


class CuratedEventsProvider:
    """Events from a local, human-checked file."""

    id = "curated"

    def __init__(self, data_dir: Path, dataset: str = "events") -> None:
        self._path = data_dir / "events" / f"{dataset}.json"
        self._feeds: list[dict] = []
        self._entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._entries = payload.get("events", [])
        self._feeds = payload.get("ics_feeds", [])

    @property
    def feeds(self) -> list[dict]:
        return self._feeds

    def upcoming(
        self, water_body: str | None = None, today: date | None = None, limit: int = 20
    ) -> list[SailingEvent]:
        today = today or date.today()
        events: list[SailingEvent] = []

        for entry in self._entries:
            if water_body and entry.get("water_body") != water_body:
                continue
            if not entry.get("title") or not entry.get("start"):
                continue

            event = SailingEvent(
                id=str(entry.get("id") or f"{entry['title']}-{entry['start']}"),
                title=entry["title"],
                start=entry["start"],
                end=entry.get("end"),
                location=entry.get("location"),
                water_body=entry.get("water_body"),
                organiser=entry.get("organiser"),
                category=entry.get("category", "event"),
                url=entry.get("url"),
                description=entry.get("description"),
                source="curated",
                source_url=entry.get("source_url"),
                checked_at=entry.get("checked_at"),
            )
            end_date = _parse_date(event.end) or event.start_date
            if end_date and end_date < today:
                continue  # past events are history, not a plan
            events.append(event)

        events.sort(key=lambda e: e.start)
        return events[:limit]


class IcsEventsProvider:
    """Reads events from an ICS calendar a club publishes.

    A deliberately minimal parser: VEVENT blocks, SUMMARY, DTSTART, DTEND, LOCATION,
    DESCRIPTION, URL. It handles line folding, which is the one part of RFC 5545 that
    silently corrupts data if you skip it. It does not handle recurrence rules — a
    weekly club race series would show only its first entry, and pretending otherwise
    would put wrong dates in front of someone planning a trip.
    """

    id = "ics"

    def __init__(self, client: httpx.AsyncClient, timeout_s: int = 20) -> None:
        self._client = client
        self._timeout_s = timeout_s

    async def fetch(self, url: str, water_body: str | None = None) -> list[SailingEvent]:
        try:
            response = await self._client.get(url, timeout=self._timeout_s)
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return self.parse(response.text, source_url=url, water_body=water_body)

    def parse(
        self, text: str, source_url: str | None = None, water_body: str | None = None
    ) -> list[SailingEvent]:
        events: list[SailingEvent] = []
        for block in _vevent_blocks(_unfold(text)):
            summary = block.get("SUMMARY")
            start = block.get("DTSTART")
            if not summary or not start:
                continue

            events.append(
                SailingEvent(
                    id=block.get("UID") or f"{summary}-{start}",
                    title=summary,
                    start=_ics_datetime(start),
                    end=_ics_datetime(block["DTEND"]) if "DTEND" in block else None,
                    location=block.get("LOCATION"),
                    water_body=water_body,
                    organiser=block.get("ORGANIZER"),
                    category=_guess_category(summary),
                    url=block.get("URL") or source_url,
                    description=block.get("DESCRIPTION"),
                    source="ics",
                    source_url=source_url,
                )
            )
        return events


def _unfold(text: str) -> str:
    """RFC 5545 folds long lines by starting the continuation with a space or tab."""
    return re.sub(r"\r?\n[ \t]", "", text)


def _vevent_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                blocks.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()  # drop parameters like ;VALUE=DATE
        current[key] = value.replace("\\,", ",").replace("\\n", " ").strip()
    return blocks


def _ics_datetime(value: str) -> str:
    """`20260815T093000Z` or `20260815` → ISO-8601. Unparseable input is passed through."""
    digits = value.strip()
    if re.fullmatch(r"\d{8}", digits):
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    match = re.fullmatch(r"(\d{8})T(\d{6})Z?", digits)
    if match:
        d, t = match.groups()
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}T{t[0:2]}:{t[2:4]}:{t[4:6]}"
    return digits


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _guess_category(title: str) -> str:
    lowered = title.lower()
    regatta_words = ("regata", "regatta", "campionato", "trofeo", "coppa", "race")
    if any(word in lowered for word in regatta_words):
        return "regatta"
    if any(word in lowered for word in ("corso", "course", "scuola", "clinic", "training")):
        return "course"
    if any(word in lowered for word in ("festa", "cena", "premiazione", "social")):
        return "social"
    return "event"


def merge_events(groups: list[list[SailingEvent]], limit: int = 20) -> list[SailingEvent]:
    """Merge several sources, dropping duplicates by (title, start day)."""
    seen: set[tuple[str, str]] = set()
    merged: list[SailingEvent] = []
    for group in groups:
        for event in group:
            key = (event.title.strip().lower(), event.start[:10])
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    merged.sort(key=lambda e: e.start)
    return merged[:limit]


def upcoming_only(events: list[SailingEvent], today: date | None = None) -> list[SailingEvent]:
    today = today or date.today()
    result = []
    for event in events:
        end = _parse_date(event.end) or event.start_date
        if end is None or end >= today:
            result.append(event)
    return result


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
