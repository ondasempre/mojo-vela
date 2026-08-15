"""Configuration. Environment only — never hardcoded, never committed (NFR-S-01)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw and raw.strip().lstrip("-").isdigit() else default


@dataclass(frozen=True)
class Settings:
    #: "auto" uses Open-Meteo and falls back to fixtures if it is unreachable.
    #: "open-meteo" forces real data (errors surface). "fixture" forces demo mode.
    weather_provider: str = os.environ.get("SAILWISE_WEATHER_PROVIDER", "auto")

    data_dir: Path = Path(os.environ.get("SAILWISE_DATA_DIR", str(REPO_ROOT / "data")))
    spots_dataset: str = os.environ.get("SAILWISE_SPOTS_DATASET", "italian_lakes")

    #: Resolve spot coordinates through Nominatim when the dataset has none.
    #: Rate-limited to the public usage policy. Disable to stay fully offline.
    geocoding_enabled: bool = _env_bool("SAILWISE_GEOCODING", True)

    forecast_ttl_s: int = _env_int("SAILWISE_FORECAST_TTL_S", 900)  # 15 min
    geocode_ttl_s: int = _env_int("SAILWISE_GEOCODE_TTL_S", 30 * 24 * 3600)  # 30 days
    http_timeout_s: int = _env_int("SAILWISE_HTTP_TIMEOUT_S", 20)

    #: Cap on spots scored per request, so one request cannot fan out unbounded.
    max_spots_per_request: int = _env_int("SAILWISE_MAX_SPOTS", 30)

    host: str = os.environ.get("SAILWISE_HOST", "127.0.0.1")
    port: int = _env_int("SAILWISE_PORT", 8000)

    #: Sent to Nominatim as required by its usage policy.
    user_agent: str = os.environ.get(
        "SAILWISE_USER_AGENT",
        "SailWise/0.2 (open-source sailing planner; https://github.com/ondasempre/mojo-vela)",
    )

    @property
    def geocode_cache_file(self) -> Path:
        return self.data_dir / "spots" / ".geocode_cache.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
