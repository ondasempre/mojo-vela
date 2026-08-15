"""Loading of synthetic test fixtures.

Fixtures are SYNTHETIC by design: deterministic, offline, and free of any provider's
terms of use. Nothing in ``data/fixtures/`` is a claim about real weather at a real
place, and every fixture file says so in its own ``warning`` field.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .score import AccessibilityInput
from .weather import HourlyWeather


def data_dir() -> Path:
    """Locate ``data/`` — overridable so the package works from anywhere."""
    env = os.environ.get("SAILWISE_DATA_DIR")
    if env:
        return Path(env)
    # python/src/sailwise_ref/fixtures.py -> repo root is three parents up
    return Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class DayFixture:
    id: str
    spot_id: str
    spot_name: str
    date: str
    hours: list[HourlyWeather]
    accessibility: AccessibilityInput


def load_day(name: str = "day_dervio_synthetic") -> DayFixture:
    path = data_dir() / "fixtures" / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    hours = [
        HourlyWeather(
            hour=int(h["hour"]),
            wind_kn=float(h["wind_kn"]),
            gust_kn=float(h["gust_kn"]),
            wind_dir_deg=float(h.get("wind_dir_deg", 0.0)),
            temp_c=float(h.get("temp_c", 20.0)),
            precip_mm=float(h.get("precip_mm", 0.0)),
            precip_prob=float(h.get("precip_prob", 0.0)),
            cloud_frac=float(h.get("cloud_frac", 0.0)),
            visibility_m=float(h.get("visibility_m", 10_000.0)),
            storm_prob=float(h.get("storm_prob", 0.0)),
        )
        for h in raw["hours"]
    ]

    acc = raw.get("accessibility", {})
    accessibility = AccessibilityInput(
        launch=_opt(acc.get("launch")),
        parking=_opt(acc.get("parking")),
        drive=_opt(acc.get("drive")),
        services=_opt(acc.get("services")),
    )

    return DayFixture(
        id=raw["id"],
        spot_id=raw["spot_id"],
        spot_name=raw["spot_name"],
        date=raw["date"],
        hours=hours,
        accessibility=accessibility,
    )


def _opt(value: object) -> float | None:
    return None if value is None else float(value)
