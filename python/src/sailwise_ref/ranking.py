"""Multi-spot ranking (Milestone 3).

"Where should I sail today?" — the primary use case (UC-1).

Specification: docs/05-algorithms.md, "Ranking algorithm".

Stage 1 filters, stage 2 scores, stage 3 combines, stage 4 selects, stage 5 explains.
A spot removed by a filter is reported **with its reason** rather than silently
dropped: "Colico is 112 km away, past your 100 km limit" is useful; a spot vanishing
from a list is not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import constants as K
from .profiles import SailingProfile
from .safety import SafetyReport, evaluate_safety, is_recommended
from .score import AccessibilityInput, ScoreResult, sailing_score
from .weather import HourlyWeather
from .window import WindowResult, best_window

EARTH_RADIUS_KM = 6371.0

#: Roads are not straight lines. Applied to straight-line distance to approximate
#: road distance until a routing provider exists (M7). Always labelled ESTIMATED.
DETOUR_FACTOR = 1.35

#: Average speed assumed for the drive-time estimate, in km/h. Deliberately
#: pessimistic for lakeside roads.
ASSUMED_SPEED_KMH = 50.0


@dataclass(frozen=True)
class SpotInput:
    """Everything the ranker needs about one candidate spot."""

    id: str
    name: str
    lat: float | None
    lon: float | None
    hours: list[HourlyWeather]
    water_body: str | None = None
    accessibility: AccessibilityInput = field(default_factory=AccessibilityInput)
    #: Facility flags; None means UNKNOWN and never satisfies a hard requirement.
    has_ramp: bool | None = None
    #: Mean of the user's past ratings (0-10) and how many, for the affinity term.
    rating_mean: float | None = None
    rating_count: int = 0
    verified: bool = False


@dataclass(frozen=True)
class Distance:
    km: float
    minutes: float
    method: str = "straight-line estimate x detour factor"
    provenance: str = "ESTIMATED"


@dataclass(frozen=True)
class RankedSpot:
    spot: SpotInput
    score: ScoreResult
    window: WindowResult
    safety: SafetyReport
    distance: Distance | None
    affinity: float
    rank_score: float
    recommended: bool

    def as_dict(self) -> dict:
        w = self.window.window
        return {
            "spot": {
                "id": self.spot.id,
                "name": self.spot.name,
                "water_body": self.spot.water_body,
                "lat": self.spot.lat,
                "lon": self.spot.lon,
                "verified": self.spot.verified,
            },
            "sailing_score": round(self.score.total, 1),
            "rank_score": round(self.rank_score, 1),
            "confidence": round(self.score.confidence, 2),
            "recommended": self.recommended,
            "components": [
                {
                    "id": c.id,
                    "raw": None if c.raw is None else round(c.raw, 3),
                    "weight": c.weight,
                    "points": round(c.points, 2),
                    "max_points": round(c.max_points, 2),
                    "known": c.raw is not None,
                }
                for c in self.score.components
            ],
            "wind": {
                "mean_kn": round(self.score.wind.mean_kn, 1),
                "max_kn": round(self.score.wind.max_kn, 1),
                "gust_max_kn": round(self.score.wind.gust_max_kn, 1),
                "gust_factor": round(self.score.wind.gust_factor, 2),
                "consistency": round(self.score.wind.consistency, 2),
                "trend": self.score.wind.trend,
            },
            "best_window": None
            if w is None
            else {
                "start": f"{w.start_hour:02d}:00",
                "end": f"{w.end_hour:02d}:00",
                "duration_h": w.duration_h,
                "quality": round(w.mean_suitability, 3),
            },
            "window_note": self.window.note,
            "distance": None
            if self.distance is None
            else {
                "km": round(self.distance.km, 1),
                "minutes": round(self.distance.minutes),
                "method": self.distance.method,
                "provenance": self.distance.provenance,
            },
            "affinity": round(self.affinity, 2),
            "safety": self.safety.as_dict(),
            "hourly": [
                {
                    "hour": h.hour,
                    "wind_kn": round(h.wind_kn, 1),
                    "gust_kn": round(h.gust_kn, 1),
                    "wind_dir_deg": round(h.wind_dir_deg),
                    "temp_c": round(h.temp_c, 1),
                    "precip_mm": round(h.precip_mm, 2),
                    "storm_prob": round(h.storm_prob, 2),
                    "suitability": round(s.value, 3),
                    "excluded": s.excluded,
                    "excluded_reason": s.reason,
                }
                for h, s in zip(self.spot.hours, self.window.hourly, strict=True)
            ],
        }


@dataclass(frozen=True)
class ExcludedSpot:
    id: str
    name: str
    reason: str

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "reason": self.reason}


@dataclass(frozen=True)
class RankingResult:
    results: list[RankedSpot]
    excluded: list[ExcludedSpot]

    def as_dict(self) -> dict:
        return {
            "results": [r.as_dict() for r in self.results],
            "excluded": [e.as_dict() for e in self.excluded],
        }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_drive(
    origin: tuple[float, float] | None, lat: float | None, lon: float | None
) -> Distance | None:
    """Straight-line distance inflated by a detour factor. Explicitly an ESTIMATE.

    This is not a route. It exists so that "within 100 km" means something before the
    routing adapter arrives (M7), and it is labelled everywhere it surfaces so nobody
    mistakes it for a driving time.
    """
    if origin is None or lat is None or lon is None:
        return None
    straight = haversine_km(origin[0], origin[1], lat, lon)
    road = straight * DETOUR_FACTOR
    return Distance(km=road, minutes=road / ASSUMED_SPEED_KMH * 60.0)


def affinity_for(rating_mean: float | None, rating_count: int) -> float:
    """Bayesian shrinkage toward the prior, so one lucky day does not crown a spot."""
    if rating_mean is None or rating_count <= 0:
        return K.PRIOR_AFFINITY
    observed = rating_mean / 10.0
    return (rating_count * observed + K.PRIOR_WEIGHT * K.PRIOR_AFFINITY) / (
        rating_count + K.PRIOR_WEIGHT
    )


def rank_spots(
    spots: list[SpotInput],
    profile: SailingProfile,
    *,
    origin: tuple[float, float] | None = None,
    max_driving_km: float | None = None,
    min_duration_h: int = 2,
    needs_ramp: bool = False,
    gust_limit_kn: float | None = None,
    limit: int | None = None,
) -> RankingResult:
    """Rank candidate spots for one request."""
    ranked: list[RankedSpot] = []
    excluded: list[ExcludedSpot] = []

    for spot in spots:
        # --- stage 1: hard filters, before any expensive work -------------
        if not spot.hours:
            excluded.append(ExcludedSpot(spot.id, spot.name, "no forecast available"))
            continue

        distance = estimate_drive(origin, spot.lat, spot.lon)
        if max_driving_km is not None and distance is not None and distance.km > max_driving_km:
            excluded.append(
                ExcludedSpot(
                    spot.id,
                    spot.name,
                    f"about {distance.km:.0f} km away, past your {max_driving_km:.0f} km limit",
                )
            )
            continue

        if needs_ramp and spot.has_ramp is not True:
            reason = (
                "no launch ramp recorded"
                if spot.has_ramp is False
                else "launch ramp unknown — not assumed present"
            )
            excluded.append(ExcludedSpot(spot.id, spot.name, reason))
            continue

        # --- stage 2: score, window, safety -------------------------------
        access = spot.accessibility
        if distance is not None and max_driving_km:
            access = AccessibilityInput(
                launch=access.launch,
                parking=access.parking,
                drive=max(0.0, 1.0 - distance.km / max_driving_km),
                services=access.services,
            )

        score = sailing_score(spot.hours, profile, access)
        window = best_window(spot.hours, profile, min_duration_h, gust_limit_kn)
        safety = evaluate_safety(spot.hours, profile, gust_limit_kn)

        # --- stage 3: combine ---------------------------------------------
        affinity = affinity_for(spot.rating_mean, spot.rating_count)
        access_component = score.component("accessibility")
        access_score = 0.0 if access_component.raw is None else access_component.raw * 100.0

        if access_component.raw is None:
            # Accessibility is unknown: renormalise rather than scoring it zero.
            weight_sum = K.RANK_W_SAIL + K.RANK_W_AFFIN
            rank_score = (
                K.RANK_W_SAIL * score.total + K.RANK_W_AFFIN * affinity * 100.0
            ) / weight_sum
        else:
            rank_score = (
                K.RANK_W_SAIL * score.total
                + K.RANK_W_ACCESS * access_score
                + K.RANK_W_AFFIN * affinity * 100.0
            )

        ranked.append(
            RankedSpot(
                spot=spot,
                score=score,
                window=window,
                safety=safety,
                distance=distance,
                affinity=affinity,
                rank_score=rank_score,
                recommended=is_recommended(score.total, safety),
            )
        )

    # --- stage 4: order ---------------------------------------------------
    ranked.sort(key=lambda r: (-r.rank_score, r.spot.name))
    if limit is not None:
        ranked = ranked[:limit]

    return RankingResult(results=ranked, excluded=excluded)


def explain_pair(better: RankedSpot, worse: RankedSpot) -> list[dict]:
    """Why one spot ranked above another, as component contribution deltas (FR-R-05)."""
    deltas = []
    for a, b in zip(better.score.components, worse.score.components, strict=True):
        delta = a.points - b.points
        if abs(delta) > 1e-9:
            deltas.append({"component": a.id, "delta_points": round(delta, 2)})
    deltas.sort(key=lambda d: abs(d["delta_points"]), reverse=True)
    return deltas
