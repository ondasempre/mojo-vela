"""Safety gates (Milestone 2).

**This module never imports the scoring weights, and the score never imports this
module.** That separation is the whole point (FR-Z-01, FR-Z-02): a warning is a
statement about conditions, not a term in an optimisation. No weight configuration,
no profile, and no high score can remove one.

Specification: docs/05-algorithms.md, "Safety gates".

These thresholds are conservative defaults, not regulation, and they are not a
substitute for official forecasts, port authority notices, or the judgement of
whoever is responsible for the boat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .profiles import SailingProfile
from .weather import HourlyWeather

#: Minutes subtracted from the first deteriorating hour to produce `return_by`.
SAFETY_MARGIN_MIN = 30

GUST_CRITICAL_FACTOR = 1.3
STORM_CAUTION_PROB = 0.30
STORM_CRITICAL_PROB = 0.50
VIS_CAUTION_M = 3_000.0
VIS_CRITICAL_M = 1_000.0
RAPID_INCREASE_KN = 8.0

DISCLAIMER = (
    "SailWise is decision support, not a safety clearance. Always verify official "
    "weather forecasts, navigational warnings and local safety information before "
    "departure."
)


class Severity(StrEnum):
    INFO = "INFO"
    CAUTION = "CAUTION"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Warning_:
    """A warning, with the numbers that produced it kept separate from the prose.

    `message` is the English fallback; `params` carries the same facts as data so a
    client can render them in its own language without the engine knowing about
    locales. Translating by re-parsing a formatted sentence is how you end up with
    "23 kn" turning into "23 nodi" in one place and not another.
    """

    code: str
    severity: Severity
    message: str
    recommendation: str | None = None
    from_hour: int | None = None
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "recommendation": self.recommendation,
            "from_hour": self.from_hour,
            "params": self.params,
        }


@dataclass(frozen=True)
class SafetyReport:
    warnings: list[Warning_]
    return_by_hour: int | None
    return_by_minute: int
    disclaimer: str = DISCLAIMER

    @property
    def has_critical(self) -> bool:
        return any(w.severity is Severity.CRITICAL for w in self.warnings)

    @property
    def worst_severity(self) -> Severity | None:
        for level in (Severity.CRITICAL, Severity.CAUTION, Severity.INFO):
            if any(w.severity is level for w in self.warnings):
                return level
        return None

    @property
    def return_by_label(self) -> str | None:
        if self.return_by_hour is None:
            return None
        return f"{self.return_by_hour:02d}:{self.return_by_minute:02d}"

    def as_dict(self) -> dict:
        return {
            "warnings": [w.as_dict() for w in self.warnings],
            "return_by": self.return_by_label,
            "has_critical": self.has_critical,
            "worst_severity": self.worst_severity.value if self.worst_severity else None,
            "disclaimer": self.disclaimer,
        }


def evaluate_safety(
    hours: list[HourlyWeather],
    profile: SailingProfile,
    gust_limit_kn: float | None = None,
) -> SafetyReport:
    """Run every gate over the forecast and collect the warnings."""
    if not hours:
        raise ValueError("evaluate_safety requires at least one hour of forecast")

    limit = profile.gust_limit_kn if gust_limit_kn is None else gust_limit_kn
    band = profile.wind_band_kn
    warnings: list[Warning_] = []

    speeds = [h.wind_kn for h in hours]
    mean_wind = sum(speeds) / len(speeds)
    max_wind = max(speeds)

    # --- wind -------------------------------------------------------------
    if mean_wind < band.a:
        warnings.append(
            Warning_(
                code="INSUFFICIENT_WIND",
                severity=Severity.INFO,
                message=(
                    f"Average wind {mean_wind:.1f} kn is below the {band.a:.0f} kn "
                    "you need for this kind of sailing."
                ),
                recommendation="Consider a later day, or a different kind of outing.",
                params={"mean_kn": round(mean_wind, 1), "min_kn": band.a},
            )
        )

    gust_hour = _first_hour_where(hours, lambda h: h.gust_kn > limit)
    if gust_hour is not None:
        gust_max = max(h.gust_kn for h in hours)
        critical = gust_max > limit * GUST_CRITICAL_FACTOR
        warnings.append(
            Warning_(
                code="GUST_FAR_ABOVE_LIMIT" if critical else "GUST_ABOVE_LIMIT",
                severity=Severity.CRITICAL if critical else Severity.CAUTION,
                message=(
                    f"Gusts up to {gust_max:.0f} kn expected from {gust_hour:02d}:00, "
                    f"above your {limit:.0f} kn limit."
                ),
                recommendation="Plan to be ashore before conditions build.",
                from_hour=gust_hour,
                params={"gust_max_kn": round(gust_max, 1), "limit_kn": limit},
            )
        )

    if max_wind > band.d:
        warnings.append(
            Warning_(
                code="WIND_ABOVE_RANGE",
                severity=Severity.CAUTION,
                message=(
                    f"Peak wind {max_wind:.0f} kn is above the top of your "
                    f"{band.a:.0f}–{band.d:.0f} kn range."
                ),
                from_hour=_first_hour_where(hours, lambda h: h.wind_kn > band.d),
                params={"max_kn": round(max_wind, 1), "band_min_kn": band.a, "band_max_kn": band.d},
            )
        )

    rapid_hour = _first_rapid_increase(hours)
    if rapid_hour is not None:
        warnings.append(
            Warning_(
                code="RAPID_WIND_INCREASE",
                severity=Severity.CAUTION,
                message=(
                    f"Wind increases by {RAPID_INCREASE_KN:.0f} kn or more within an "
                    f"hour around {rapid_hour:02d}:00."
                ),
                recommendation="Reef early rather than late.",
                from_hour=rapid_hour,
                params={"delta_kn": RAPID_INCREASE_KN},
            )
        )

    # --- thunderstorms ----------------------------------------------------
    storm_max = max(h.storm_prob for h in hours)
    if storm_max >= STORM_CRITICAL_PROB:
        hour = _first_hour_where(hours, lambda h: h.storm_prob >= STORM_CRITICAL_PROB)
        warnings.append(
            Warning_(
                code="THUNDERSTORM_LIKELY",
                severity=Severity.CRITICAL,
                message=f"Thunderstorm probability reaches {storm_max:.0%} from {hour:02d}:00.",
                recommendation="Do not plan to be on the water in this period.",
                from_hour=hour,
                params={"probability": round(storm_max, 2)},
            )
        )
    elif storm_max >= STORM_CAUTION_PROB:
        hour = _first_hour_where(hours, lambda h: h.storm_prob >= STORM_CAUTION_PROB)
        warnings.append(
            Warning_(
                code="THUNDERSTORM_RISK",
                severity=Severity.CAUTION,
                message=f"Thunderstorm probability reaches {storm_max:.0%} from {hour:02d}:00.",
                recommendation="Watch the sky to windward and keep an escape route.",
                from_hour=hour,
                params={"probability": round(storm_max, 2)},
            )
        )

    # --- visibility -------------------------------------------------------
    known_vis = [h for h in hours if h.visibility_m is not None]
    if known_vis:
        vis_min = min(h.visibility_m for h in known_vis)
        if vis_min < VIS_CRITICAL_M:
            warnings.append(
                Warning_(
                    code="VISIBILITY_LOW",
                    severity=Severity.CRITICAL,
                    message=f"Visibility drops to {vis_min:.0f} m.",
                    recommendation=(
                        "Do not leave the shore without instruments and local knowledge."
                    ),
                    from_hour=_first_hour_where(hours, _below(VIS_CRITICAL_M)),
                    params={"visibility_m": round(vis_min)},
                )
            )
        elif vis_min < VIS_CAUTION_M:
            warnings.append(
                Warning_(
                    code="VISIBILITY_REDUCED",
                    severity=Severity.CAUTION,
                    message=f"Visibility drops to {vis_min:.0f} m.",
                    from_hour=_first_hour_where(hours, _below(VIS_CAUTION_M)),
                    params={"visibility_m": round(vis_min)},
                )
            )

    return_hour, return_minute = _return_by(warnings)
    return SafetyReport(
        warnings=warnings, return_by_hour=return_hour, return_by_minute=return_minute
    )


def is_recommended(score_total: float, report: SafetyReport, threshold: float = 60.0) -> bool:
    """A CRITICAL warning vetoes the recommendation at any score (FR-Z-02)."""
    return score_total >= threshold and not report.has_critical


def _below(threshold_m: float):
    """Predicate: visibility known and below the threshold. Unknown never matches."""

    def predicate(hour: HourlyWeather) -> bool:
        return hour.visibility_m is not None and hour.visibility_m < threshold_m

    return predicate


def _first_hour_where(hours: list[HourlyWeather], predicate) -> int | None:
    for h in hours:
        if predicate(h):
            return h.hour
    return None


def _first_rapid_increase(hours: list[HourlyWeather]) -> int | None:
    for i in range(len(hours) - 1):
        if hours[i + 1].wind_kn - hours[i].wind_kn >= RAPID_INCREASE_KN:
            return hours[i + 1].hour
    return None


def _return_by(warnings: list[Warning_]) -> tuple[int | None, int]:
    """Earliest deteriorating hour minus the safety margin.

    Only gust and thunderstorm gates set a return time: those are the conditions that
    make getting back harder the longer you wait.
    """
    triggering = [
        w.from_hour
        for w in warnings
        if w.from_hour is not None
        and w.severity in (Severity.CAUTION, Severity.CRITICAL)
        and w.code.startswith(("GUST_", "THUNDERSTORM_"))
    ]
    if not triggering:
        return None, 0

    total_minutes = min(triggering) * 60 - SAFETY_MARGIN_MIN
    if total_minutes < 0:
        return 0, 0
    return total_minutes // 60, total_minutes % 60
