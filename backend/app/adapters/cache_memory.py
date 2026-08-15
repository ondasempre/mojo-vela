"""In-process TTL cache with stale-serving.

Milestone 5 replaces this with Redis behind the same port; the semantics here are
deliberately the ones Redis will have to reproduce, so the swap changes one class:

* a hit reports its age, and the UI shows it (FR-C-04);
* an expired entry is not deleted — it can still be served as STALE when the
  provider is unreachable (FR-C-05), because a forecast from 40 minutes ago clearly
  labelled is far more useful than an error;
* nothing is ever fabricated to fill a gap (NFR-R-03).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from ..ports import CacheInfo

#: Bump to invalidate everything at once after a schema change.
CACHE_VERSION = "v1"


@dataclass
class _Entry:
    value: object
    stored_at: float
    ttl_s: int
    hits: int = 0


class MemoryCache:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._hits = 0
        self._misses = 0
        self._stale_served = 0

    def get(self, key: str) -> tuple[object, CacheInfo] | None:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        age = int(time.time() - entry.stored_at)
        if age >= entry.ttl_s:
            self._misses += 1
            return None
        entry.hits += 1
        self._hits += 1
        return entry.value, CacheInfo(state="HIT", age_s=age, ttl_s=entry.ttl_s)

    def get_stale(self, key: str) -> tuple[object, CacheInfo] | None:
        """Serve an expired entry, clearly marked. Used only when a provider fails."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._stale_served += 1
        age = int(time.time() - entry.stored_at)
        return entry.value, CacheInfo(state="STALE", age_s=age, ttl_s=entry.ttl_s)

    def set(self, key: str, value: object, ttl_s: int) -> None:
        self._entries[key] = _Entry(value=value, stored_at=time.time(), ttl_s=ttl_s)

    def invalidate(self, prefix: str | None = None) -> int:
        if prefix is None:
            count = len(self._entries)
            self._entries.clear()
            return count
        doomed = [k for k in self._entries if k.startswith(prefix)]
        for key in doomed:
            del self._entries[key]
        return len(doomed)

    def stats(self) -> dict:
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "stale_served": self._stale_served,
        }


def geohash_key(lat: float, lon: float, precision: int = 2) -> str:
    """Round coordinates before they become a cache key.

    Two reasons, both load-bearing. Forecasts do not differ meaningfully inside a
    ~1 km cell, so rounding collapses thousands of near-identical requests into one.
    And precise user coordinates never enter a cache key, which is a privacy control
    (docs/08-security-privacy.md), not just an optimisation.
    """
    return f"{lat:.{precision}f},{lon:.{precision}f}"


def cache_key(data_class: str, provider: str, *parts: str) -> str:
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"sw:{CACHE_VERSION}:{data_class}:{provider}:{digest}"
