"""The Sailing Score — reference implementation.

This module is the oracle. The Mojo implementation in ``mojo/src/sailwise/score.mojo``
must reproduce these numbers within 1e-9 (NFR-C-01), and every future optimisation
(SIMD, parallel) must reproduce them exactly.

Specification: docs/05-algorithms.md. Change the specification first.

Scope of v1 (Milestone 1): the seven components and their aggregation. The best
sailing window and the safety gates arrive in Milestone 2 and live in their own
modules, because a safety pipeline that shares code with the score is a safety
pipeline that can be tuned away by a weight change (FR-Z-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import constants as K
from .profiles import COMPONENT_IDS, SailingProfile
from .units import clamp01, mean, trapezoid
from .weather import HourlyWeather, WindStats, gust_excess_score, wind_stats


@dataclass(frozen=True)
class AccessibilityInput:
    """Static, non-weather inputs to the accessibility component.

    Every field is optional. ``None`` means UNKNOWN and is dropped from the weighted
    average rather than imputed as zero (FR-P-03): "we do not know whether there is a
    ramp" and "there is no ramp" are different facts and must not collapse into one.
    """

    launch: float | None = None  # 1.0 public ramp, 0.6 beach launch, 0.0 none
    parking: float | None = None  # Parking Score in [0, 1]
    drive: float | None = None  # 1.0 next door, 0.0 at the driving limit
    services: float | None = None  # saturating count of nearby services

    @staticmethod
    def from_drive_minutes(
        drive_minutes: float,
        max_drive_minutes: float,
        *,
        launch: float | None = None,
        parking: float | None = None,
        service_count: int | None = None,
    ) -> AccessibilityInput:
        drive = (
            clamp01(1.0 - drive_minutes / max_drive_minutes)
            if max_drive_minutes > 0
            else None
        )
        services = (
            clamp01(service_count / K.SERVICE_REF) if service_count is not None else None
        )
        return AccessibilityInput(
            launch=launch, parking=parking, drive=drive, services=services
        )


@dataclass(frozen=True)
class Component:
    """One scored component, with everything needed to explain it (FR-S-02)."""

    id: str
    raw: float | None  # None => UNKNOWN, excluded from aggregation
    weight: float
    points: float
    max_points: float
    confidence: float


@dataclass(frozen=True)
class ScoreResult:
    total: float
    confidence: float
    components: list[Component]
    wind: WindStats
    model_version: str = K.SCORE_MODEL_VERSION
    notes: list[str] = field(default_factory=list)

    def component(self, component_id: str) -> Component:
        for c in self.components:
            if c.id == component_id:
                return c
        raise KeyError(component_id)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "confidence": self.confidence,
            "model_version": self.model_version,
            "components": [
                {
                    "id": c.id,
                    "raw": c.raw,
                    "weight": c.weight,
                    "points": c.points,
                    "max_points": c.max_points,
                    "confidence": c.confidence,
                }
                for c in self.components
            ],
            "wind": {
                "mean_kn": self.wind.mean_kn,
                "max_kn": self.wind.max_kn,
                "gust_max_kn": self.wind.gust_max_kn,
                "stdev_kn": self.wind.stdev_kn,
                "gust_factor": self.wind.gust_factor,
                "consistency": self.wind.consistency,
                "trend": self.wind.trend,
            },
        }


# --- individual components -------------------------------------------------


def score_wind_quality(hours: list[HourlyWeather], profile: SailingProfile) -> float:
    """Half from the window mean, half from how much of the window sits in the band.

    A day averaging 12 kn because it blew 4 in the morning and 20 in the afternoon is
    not the same day as a steady 12, and a mean-only score cannot tell them apart.
    """
    b = profile.wind_band_kn
    stats_mean = mean([h.wind_kn for h in hours])
    from_mean = trapezoid(stats_mean, b.a, b.b, b.c, b.d)
    per_hour = mean([trapezoid(h.wind_kn, b.a, b.b, b.c, b.d) for h in hours])
    return K.W_MEAN_SHARE * from_mean + (1.0 - K.W_MEAN_SHARE) * per_hour


def score_wind_stability(stats: WindStats) -> float:
    steadiness = clamp01(1.0 - stats.cv / K.CV_MAX)
    gustiness = gust_excess_score(stats.gust_factor)
    return K.STAB_CV_SHARE * steadiness + (1.0 - K.STAB_CV_SHARE) * gustiness


def score_weather(hours: list[HourlyWeather]) -> float:
    """Thunderstorm risk, visibility and cloud.

    Visibility is optional: several forecast models do not publish it. When it is
    missing the term is dropped and the remaining weights are renormalised, rather
    than assuming clear air (FR-P-03). With visibility present the weights already
    sum to 1, so this path is exactly equivalent to the simple weighted sum.
    """
    storm_max = max(h.storm_prob for h in hours)
    cloud_mean = mean([h.cloud_frac for h in hours])

    terms: list[tuple[float, float]] = [
        (K.W_STORM, 1.0 - clamp01(storm_max)),
        (K.W_CLOUD, 1.0 - K.CLOUD_PENALTY * clamp01(cloud_mean)),
    ]

    known_vis = [h.visibility_m for h in hours if h.visibility_m is not None]
    if known_vis:
        vis_score = clamp01((min(known_vis) - K.VIS_BAD_M) / (K.VIS_GOOD_M - K.VIS_BAD_M))
        terms.append((K.W_VIS, vis_score))

    weight_sum = sum(w for w, _ in terms)
    return sum(w * v for w, v in terms) / weight_sum


def score_rain(hours: list[HourlyWeather]) -> float:
    total_mm = sum(h.precip_mm for h in hours)
    prob_max = max(h.precip_prob for h in hours)
    return clamp01(
        1.0
        - K.RAIN_AMOUNT_W * (total_mm / K.RAIN_REF_MM)
        - K.RAIN_PROB_W * clamp01(prob_max)
    )


def score_temperature(hours: list[HourlyWeather], profile: SailingProfile) -> float:
    t = profile.temp_band_c
    return trapezoid(mean([h.temp_c for h in hours]), t.a, t.b, t.c, t.d)


def score_water_conditions(stats: WindStats, profile: SailingProfile) -> float:
    """ESTIMATED, and it must be labelled as such wherever it is shown.

    v1 proxies surface chop from mean wind speed alone. A real model would use wind
    direction, the spot's exposed sectors and fetch length; that is roadmap item M8+.
    Until then the honest label is "estimated from wind speed", not a wave height.
    """
    chop = clamp01(
        (stats.mean_kn - K.CHOP_ONSET_KN) / (K.CHOP_FULL_KN - K.CHOP_ONSET_KN)
    )
    return clamp01(1.0 - chop * profile.chop_sensitivity)


def score_accessibility(access: AccessibilityInput) -> tuple[float | None, float]:
    """Return ``(raw, confidence)``; ``raw`` is None when nothing at all is known.

    Sub-factors that are UNKNOWN drop out of both numerator and denominator, and the
    confidence reports how much of the intended weight was actually available.
    """
    pairs = (
        (access.launch, K.ACCESS_W_LAUNCH),
        (access.parking, K.ACCESS_W_PARKING),
        (access.drive, K.ACCESS_W_DRIVE),
        (access.services, K.ACCESS_W_SERVICES),
    )
    total_weight = sum(w for _, w in pairs)
    available = [(v, w) for v, w in pairs if v is not None]
    if not available:
        return None, 0.0

    weight_sum = sum(w for _, w in available)
    raw = sum(clamp01(v) * w for v, w in available) / weight_sum
    return raw, weight_sum / total_weight


# --- aggregation -----------------------------------------------------------


def sailing_score(
    hours: list[HourlyWeather],
    profile: SailingProfile,
    access: AccessibilityInput | None = None,
) -> ScoreResult:
    """Compute the Sailing Score in [0, 100] for a window at one spot.

    Aggregation normalises by the sum of the weights of the components that were
    actually computable. That gives two properties for free: a user-edited weight set
    that does not sum to 1 is still valid (FR-S-05), and a missing component shifts
    weight onto the others instead of silently scoring zero (FR-P-03).
    """
    if not hours:
        raise ValueError("sailing_score requires at least one hour of forecast")

    access = access or AccessibilityInput()
    stats = wind_stats(hours)
    weights = profile.weights.as_tuple()
    notes: list[str] = []

    access_raw, access_conf = score_accessibility(access)
    if access_raw is None:
        notes.append(
            "accessibility UNKNOWN: no launch, parking, drive or service data available"
        )
    notes.append("water_conditions is ESTIMATED from wind speed, not a wave forecast")

    raws: list[float | None] = [
        score_wind_quality(hours, profile),
        score_wind_stability(stats),
        score_weather(hours),
        score_rain(hours),
        score_temperature(hours, profile),
        score_water_conditions(stats, profile),
        access_raw,
    ]
    confidences = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, access_conf]

    available_weight = sum(w for w, r in zip(weights, raws, strict=True) if r is not None)
    total_weight = sum(weights)
    if available_weight <= 0.0:
        raise ValueError("no component could be computed")

    weighted_sum = sum(w * r for w, r in zip(weights, raws, strict=True) if r is not None)
    total = 100.0 * weighted_sum / available_weight
    confidence = sum(w * c for w, c in zip(weights, confidences, strict=True)) / total_weight

    components = [
        Component(
            id=cid,
            raw=raw,
            weight=w,
            points=(100.0 * w * raw / available_weight) if raw is not None else 0.0,
            max_points=100.0 * w / available_weight,
            confidence=conf,
        )
        for cid, raw, w, conf in zip(COMPONENT_IDS, raws, weights, confidences, strict=True)
    ]

    return ScoreResult(
        total=total,
        confidence=confidence,
        components=components,
        wind=stats,
        notes=notes,
    )
