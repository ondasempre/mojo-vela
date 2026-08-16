"""Editorial content: winds, mooring, knots, safety.

This is the one part of SailWise that is *written* rather than computed or fetched,
so it needs its own honesty rule. Two kinds of statement live here:

* **General seamanship** — how a bowline behaves under load, why you rig fenders
  before you manoeuvre, what cold water does in the first thirty seconds. This is
  established knowledge and it is written plainly.
* **Local claims** — "the Breva enters between 10:30 and 11 at about 14–16 kn".
  These carry a `source` link on the card, and the page states that they describe a
  typical fair-weather day rather than a forecast.

Where neither applies, the content says so. The Lake Iseo entry has no wind cards
and an explicit note explaining that no sourced description was available — an empty
section with a reason beats a plausible invention.

Content lives in data/knowledge/*.json so it can be corrected, extended and
translated without touching code.
"""

from __future__ import annotations

import json
from pathlib import Path

TOPICS = ("winds", "mooring", "knots", "safety")


class KnowledgeService:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "knowledge"
        self._topics: dict[str, dict] = {}
        self._problems: list[str] = []
        self._load()

    def _load(self) -> None:
        for topic in TOPICS:
            path = self._dir / f"{topic}.json"
            if not path.exists():
                self._problems.append(f"{topic}.json non trovato")
                continue
            try:
                self._topics[topic] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                self._problems.append(f"{topic}.json: {exc}")

    @property
    def problems(self) -> list[str]:
        return self._problems

    def available(self) -> list[dict]:
        return [
            {
                "topic": topic,
                "title": payload.get("title", topic),
                "emoji": payload.get("emoji", "📘"),
            }
            for topic, payload in self._topics.items()
        ]

    def get(self, topic: str) -> dict | None:
        return self._topics.get(topic)

    def winds_for_lake(self, water_body: str) -> dict | None:
        """The wind card for one lake, so the planner can link to it in context."""
        winds = self._topics.get("winds")
        if not winds:
            return None
        for lake in winds.get("lakes", []):
            if lake.get("id") == water_body:
                return lake
        return None
