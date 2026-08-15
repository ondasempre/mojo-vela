"""Best sailing window search (Milestone 2).

Given a day's hourly forecast and a profile, find the contiguous stretch that is
actually worth being on the water for.

Specification: docs/05-algorithms.md, "Best sailing window".

This is a separate module from `score.py` on purpose: the window answers "when",
the score answers "how good", and conflating them makes both harder to explain.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profiles import SailingProfile
from .units import clamp01, trapezoid
from .weather import HourlyWeather

#: Two windows whose mean suitability differs by less than this count as tied.
WINDOW_EPS = 0.01

#: Hourly suitability sub-weights.
H_WIND_W = 0.5
H_STORM_W = 0.3
H_RAIN_W = 0.2

#: Precipitation (mm/h) at which the rain term of hourly suitability reaches 0.
H_RAIN_REF_MM = 2.0

#: An hour is excluded outright above this thunderstorm probability.
EXCLUDE_STORM_PROB = 0.5


@dataclass(frozen=True)
class HourSuitability:
    hour: int
    value: float
    excluded: bool
    reason: str | None


@dataclass(frozen=True)
class SailingWindow:
    start_hour: int
    #: Exclusive: a window over hours 11..15 ends at 16:00.
    end_hour: int
    mean_suitability: float
    duration_h: int

    @property
    def label(self) -> str:
        return f"{self.start_hour:02d}:00–{self.end_hour:02d}:00"


@dataclass(frozen=True)
class WindowResult:
    window: SailingWindow | None
    hourly: list[HourSuitability]
    #: Why no window was found, when `window` is None.
    note: str | None = None

    @property
    def excluded_hours(self) -> list[HourSuitability]:
        return [h for h in self.hourly if h.excluded]


def hour_suitability(
    hour: HourlyWeather, profile: SailingProfile, gust_limit_kn: float
) -> HourSuitability:
    """Score a single hour, and decide whether it is excluded outright.

    Exclusion is a hard mask, not a low score: an hour with gusts above the sailor's
    limit cannot be averaged away by the pleasant hours around it.
    """
    excluded = False
    reason: str | None = None
    if hour.gust_kn > gust_limit_kn:
        excluded = True
        reason = f"gusts {hour.gust_kn:.0f} kn above your {gust_limit_kn:.0f} kn limit"
    elif hour.storm_prob >= EXCLUDE_STORM_PROB:
        excluded = True
        reason = f"thunderstorm probability {hour.storm_prob:.0%}"

    b = profile.wind_band_kn
    value = (
        H_WIND_W * trapezoid(hour.wind_kn, b.a, b.b, b.c, b.d)
        + H_STORM_W * (1.0 - clamp01(hour.storm_prob))
        + H_RAIN_W * (1.0 - clamp01(hour.precip_mm / H_RAIN_REF_MM))
    )
    return HourSuitability(hour=hour.hour, value=value, excluded=excluded, reason=reason)


def best_window(
    hours: list[HourlyWeather],
    profile: SailingProfile,
    min_duration_h: int = 2,
    gust_limit_kn: float | None = None,
) -> WindowResult:
    """Find the best contiguous window of at least ``min_duration_h`` hours.

    Returns a result with ``window=None`` when no admissible window exists. That is a
    real answer -- "there is no good window today" -- and it is never faked by
    relaxing the exclusion mask.
    """
    if not hours:
        raise ValueError("best_window requires at least one hour of forecast")

    limit = profile.gust_limit_kn if gust_limit_kn is None else gust_limit_kn
    suitability = [hour_suitability(h, profile, limit) for h in hours]

    n = len(hours)
    if min_duration_h < 1:
        min_duration_h = 1
    if n < min_duration_h:
        return WindowResult(
            window=None,
            hourly=suitability,
            note=f"the available time window is shorter than {min_duration_h} h",
        )

    # Prefix sums make every candidate window an O(1) lookup.
    prefix = [0.0]
    for s in suitability:
        prefix.append(prefix[-1] + s.value)

    best: SailingWindow | None = None
    for start in range(n):
        if suitability[start].excluded:
            continue
        for end in range(start + min_duration_h, n + 1):
            # Any excluded hour inside the candidate disqualifies it.
            if suitability[end - 1].excluded:
                break
            length = end - start
            mean_value = (prefix[end] - prefix[start]) / length
            candidate = SailingWindow(
                start_hour=hours[start].hour,
                end_hour=hours[end - 1].hour + 1,
                mean_suitability=mean_value,
                duration_h=length,
            )
            if _is_better(candidate, best):
                best = candidate

    if best is None:
        return WindowResult(
            window=None,
            hourly=suitability,
            note=(
                f"no stretch of {min_duration_h} h or more is free of excluded hours "
                "(gusts above your limit, or thunderstorm risk)"
            ),
        )

    return WindowResult(window=best, hourly=suitability)


def _is_better(candidate: SailingWindow, current: SailingWindow | None) -> bool:
    """Tie-break: higher mean, then longer, then earlier (docs/05-algorithms.md)."""
    if current is None:
        return True
    delta = candidate.mean_suitability - current.mean_suitability
    if delta > WINDOW_EPS:
        return True
    if delta < -WINDOW_EPS:
        return False
    # Within epsilon: prefer the longer window, then the earlier start.
    if candidate.duration_h != current.duration_h:
        return candidate.duration_h > current.duration_h
    return candidate.start_hour < current.start_hour


__all__ = [
    "HourSuitability",
    "SailingWindow",
    "WindowResult",
    "best_window",
    "hour_suitability",
]
