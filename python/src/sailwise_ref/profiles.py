"""Sailing profiles: weights and preference bands (FR-S-03, FR-S-04).

These defaults are a starting hypothesis, not physics. They are configuration: a user
may override any of them, and the score normalises by the sum of weights so that an
edited weight set is safe by construction (FR-S-05).

Reference: docs/05-algorithms.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProfileId(StrEnum):
    RELAX = "RELAX"
    CRUISING = "CRUISING"
    TRAINING = "TRAINING"
    RACING = "RACING"
    FAMILY = "FAMILY"
    SPORT = "SPORT"


#: Canonical component order. The Mojo implementation indexes arrays in this order,
#: so it is part of the cross-language contract -- do not reorder.
COMPONENT_IDS = (
    "wind_quality",
    "wind_stability",
    "weather",
    "rain",
    "temperature",
    "water_conditions",
    "accessibility",
)


@dataclass(frozen=True)
class Band:
    """A trapezoidal preference band: zero below ``a``, ideal over ``[b, c]``, zero above ``d``."""

    a: float
    b: float
    c: float
    d: float

    def __post_init__(self) -> None:
        if not (self.a <= self.b <= self.c <= self.d):
            raise ValueError(f"band must satisfy a <= b <= c <= d, got {self}")


@dataclass(frozen=True)
class Weights:
    """Component weights. Need not sum to 1: the score normalises (FR-S-05)."""

    wind_quality: float
    wind_stability: float
    weather: float
    rain: float
    temperature: float
    water_conditions: float
    accessibility: float

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.wind_quality,
            self.wind_stability,
            self.weather,
            self.rain,
            self.temperature,
            self.water_conditions,
            self.accessibility,
        )

    def __post_init__(self) -> None:
        if any(w < 0.0 for w in self.as_tuple()):
            raise ValueError("weights must be non-negative")
        if sum(self.as_tuple()) <= 0.0:
            raise ValueError("at least one weight must be positive")


@dataclass(frozen=True)
class SailingProfile:
    """Everything the scoring model needs to know about what this sailor wants."""

    id: ProfileId
    weights: Weights
    wind_band_kn: Band
    temp_band_c: Band
    #: How much this sailor dislikes a choppy surface, in [0, 1].
    chop_sensitivity: float
    #: Gust ceiling used by the safety gates (M2). Not used by the score itself.
    gust_limit_kn: float


PROFILES: dict[ProfileId, SailingProfile] = {
    ProfileId.RELAX: SailingProfile(
        id=ProfileId.RELAX,
        weights=Weights(0.22, 0.22, 0.16, 0.10, 0.14, 0.11, 0.05),
        wind_band_kn=Band(3, 6, 12, 18),
        temp_band_c=Band(5, 18, 30, 38),
        chop_sensitivity=0.80,
        gust_limit_kn=18.0,
    ),
    ProfileId.CRUISING: SailingProfile(
        id=ProfileId.CRUISING,
        weights=Weights(0.30, 0.20, 0.20, 0.05, 0.10, 0.05, 0.10),
        wind_band_kn=Band(4, 8, 16, 22),
        temp_band_c=Band(5, 18, 30, 38),
        chop_sensitivity=0.60,
        gust_limit_kn=22.0,
    ),
    ProfileId.TRAINING: SailingProfile(
        id=ProfileId.TRAINING,
        weights=Weights(0.34, 0.28, 0.14, 0.06, 0.06, 0.06, 0.06),
        wind_band_kn=Band(5, 10, 18, 25),
        temp_band_c=Band(5, 16, 30, 38),
        chop_sensitivity=0.35,
        gust_limit_kn=26.0,
    ),
    ProfileId.RACING: SailingProfile(
        id=ProfileId.RACING,
        weights=Weights(0.38, 0.30, 0.12, 0.04, 0.03, 0.07, 0.06),
        wind_band_kn=Band(5, 10, 20, 30),
        temp_band_c=Band(0, 12, 30, 40),
        chop_sensitivity=0.20,
        gust_limit_kn=30.0,
    ),
    ProfileId.FAMILY: SailingProfile(
        id=ProfileId.FAMILY,
        weights=Weights(0.18, 0.22, 0.18, 0.12, 0.14, 0.10, 0.06),
        wind_band_kn=Band(2, 5, 10, 15),
        temp_band_c=Band(12, 20, 30, 36),
        chop_sensitivity=0.90,
        gust_limit_kn=14.0,
    ),
    ProfileId.SPORT: SailingProfile(
        id=ProfileId.SPORT,
        weights=Weights(0.36, 0.16, 0.14, 0.06, 0.06, 0.12, 0.10),
        wind_band_kn=Band(8, 14, 24, 33),
        temp_band_c=Band(5, 16, 30, 38),
        chop_sensitivity=0.30,
        gust_limit_kn=32.0,
    ),
}


def get_profile(profile_id: ProfileId | str) -> SailingProfile:
    if isinstance(profile_id, str):
        profile_id = ProfileId(profile_id)
    return PROFILES[profile_id]
