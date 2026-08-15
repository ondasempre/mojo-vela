"""Normalised weather records and wind statistics.

This module is the compute-side view of the forecast: plain numbers in canonical
units, with no provider, no HTTP and no JSON in sight. Adapters normalise into it.

Reference: docs/04-data-model.md, docs/05-algorithms.md
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    CV_MAX,
    GUST_EXCESS_MAX,
    MEAN_WIND_FLOOR_KN,
    TREND_SLOPE_KN_PER_H,
)
from .units import clamp01, least_squares_slope, mean, stdev_population


@dataclass(frozen=True)
class HourlyWeather:
    """One hour of normalised forecast at one location.

    Wind in knots, direction in meteorological degrees (the direction the wind comes
    FROM), temperature in Celsius, precipitation in mm for that hour, probabilities
    and fractions in [0, 1], visibility in metres.
    """

    hour: int
    wind_kn: float
    gust_kn: float
    wind_dir_deg: float = 0.0  # carried through the model; unused by scoring v1
    temp_c: float = 20.0
    precip_mm: float = 0.0
    precip_prob: float = 0.0
    cloud_frac: float = 0.0
    visibility_m: float = 10_000.0
    storm_prob: float = 0.0


class WindTrend(str):
    RISING = "RISING"
    EASING = "EASING"
    STEADY = "STEADY"
    RISING_THEN_EASING = "RISING_THEN_EASING"
    EASING_THEN_RISING = "EASING_THEN_RISING"


@dataclass(frozen=True)
class WindStats:
    """Descriptive statistics for the wind over a scoring window (FR-S-09)."""

    mean_kn: float
    max_kn: float
    min_kn: float
    gust_max_kn: float
    gust_mean_kn: float
    stdev_kn: float
    cv: float
    gust_factor: float
    consistency: float
    slope_kn_per_h: float
    trend: str


def wind_stats(hours: list[HourlyWeather]) -> WindStats:
    """Compute the wind statistics for a window.

    The ``MEAN_WIND_FLOOR_KN`` guard matters: with a near-calm forecast the
    coefficient of variation explodes and the gust factor divides by ~0. Rather than
    emit a NaN that would poison the score, the statistics fall back to neutral
    values -- the wind_quality component has already collapsed to ~0 in that case, so
    steadiness is not the interesting signal anyway.
    """
    if not hours:
        raise ValueError("wind_stats requires at least one hour")

    speeds = [h.wind_kn for h in hours]
    gusts = [h.gust_kn for h in hours]

    m = mean(speeds)
    sd = stdev_population(speeds)
    gm = mean(gusts)

    if m >= MEAN_WIND_FLOOR_KN:
        cv = sd / m
        gust_factor = gm / m
    else:
        cv = 1.0
        gust_factor = 1.0

    consistency = clamp01(1.0 - cv / CV_MAX)
    slope = least_squares_slope(speeds)

    return WindStats(
        mean_kn=m,
        max_kn=max(speeds),
        min_kn=min(speeds),
        gust_max_kn=max(gusts),
        gust_mean_kn=gm,
        stdev_kn=sd,
        cv=cv,
        gust_factor=gust_factor,
        consistency=consistency,
        slope_kn_per_h=slope,
        trend=_classify_trend(speeds, slope),
    )


def _classify_trend(speeds: list[float], slope: float) -> str:
    """Classify the shape of the day.

    A thermal lake breeze typically builds through the morning and dies in the late
    afternoon, so a single overall slope would report "steady" for the most
    characteristic day on Lake Como. Splitting the window in half catches it.
    """
    n = len(speeds)
    if n >= 4:
        half = n // 2
        s1 = least_squares_slope(speeds[:half])
        s2 = least_squares_slope(speeds[half:])
        if s1 >= TREND_SLOPE_KN_PER_H and s2 <= -TREND_SLOPE_KN_PER_H:
            return WindTrend.RISING_THEN_EASING
        if s1 <= -TREND_SLOPE_KN_PER_H and s2 >= TREND_SLOPE_KN_PER_H:
            return WindTrend.EASING_THEN_RISING

    if slope >= TREND_SLOPE_KN_PER_H:
        return WindTrend.RISING
    if slope <= -TREND_SLOPE_KN_PER_H:
        return WindTrend.EASING
    return WindTrend.STEADY


def gust_excess_score(gust_factor: float) -> float:
    """Sub-score in [0, 1] for gustiness: 1.0 when gusts equal the mean wind."""
    return clamp01(1.0 - (gust_factor - 1.0) / GUST_EXCESS_MAX)
