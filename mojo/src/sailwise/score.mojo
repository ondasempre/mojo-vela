"""The Sailing Score — Mojo implementation.

Mirrors python/src/sailwise_ref/score.py, which is the oracle. The two must agree
within 1e-9 on the golden fixtures (NFR-C-01); mojo/tests/test_score.mojo proves it.

Specification: docs/05-algorithms.md.

Scope of Milestone 1: the seven components and their aggregation. The best-window
search (milestone 2) and the safety gates (milestone 2) live in their own modules —
a safety pipeline that shares code with the score is a safety pipeline that a weight
change can quietly disable.
"""

from .units import clamp01, mean, trapezoid
from .weather import (
    HourlyWeather,
    WindStats,
    compute_wind_stats,
    gust_excess_score,
)

# --- constants (mirror python/src/sailwise_ref/constants.py) ----------------

alias SCORE_MODEL_VERSION: StaticString = "1.0.0"

alias CV_MAX: Float64 = 0.60
alias W_MEAN_SHARE: Float64 = 0.5
alias STAB_CV_SHARE: Float64 = 0.6

alias VIS_BAD_M: Float64 = 1000.0
alias VIS_GOOD_M: Float64 = 10000.0
alias CLOUD_PENALTY: Float64 = 0.6
alias W_STORM: Float64 = 0.50
alias W_VIS: Float64 = 0.25
alias W_CLOUD: Float64 = 0.25

alias RAIN_AMOUNT_W: Float64 = 0.6
alias RAIN_PROB_W: Float64 = 0.4
alias RAIN_REF_MM: Float64 = 5.0

alias CHOP_ONSET_KN: Float64 = 12.0
alias CHOP_FULL_KN: Float64 = 30.0

alias ACCESS_W_LAUNCH: Float64 = 0.40
alias ACCESS_W_PARKING: Float64 = 0.25
alias ACCESS_W_DRIVE: Float64 = 0.20
alias ACCESS_W_SERVICES: Float64 = 0.15
alias SERVICE_REF: Float64 = 4.0

alias RECOMMEND_THRESHOLD: Float64 = 60.0

# Canonical component order. It is part of the cross-language contract: the Python
# side indexes the same positions. Do not reorder.
alias C_WIND_QUALITY: Int = 0
alias C_WIND_STABILITY: Int = 1
alias C_WEATHER: Int = 2
alias C_RAIN: Int = 3
alias C_TEMPERATURE: Int = 4
alias C_WATER: Int = 5
alias C_ACCESSIBILITY: Int = 6
alias N_COMPONENTS: Int = 7


@fieldwise_init
struct Band(Copyable, Movable):
    """A trapezoidal preference band: zero below `a`, ideal over [b, c], zero above `d`."""

    var a: Float64
    var b: Float64
    var c: Float64
    var d: Float64


@fieldwise_init
struct Weights(Copyable, Movable):
    """Component weights. They need not sum to 1: the score normalises (FR-S-05)."""

    var wind_quality: Float64
    var wind_stability: Float64
    var weather: Float64
    var rain: Float64
    var temperature: Float64
    var water_conditions: Float64
    var accessibility: Float64

    fn get(self, index: Int) -> Float64:
        if index == C_WIND_QUALITY:
            return self.wind_quality
        if index == C_WIND_STABILITY:
            return self.wind_stability
        if index == C_WEATHER:
            return self.weather
        if index == C_RAIN:
            return self.rain
        if index == C_TEMPERATURE:
            return self.temperature
        if index == C_WATER:
            return self.water_conditions
        return self.accessibility

    fn total(self) -> Float64:
        return (
            self.wind_quality
            + self.wind_stability
            + self.weather
            + self.rain
            + self.temperature
            + self.water_conditions
            + self.accessibility
        )


@fieldwise_init
struct SailingProfile(Copyable, Movable):
    """Everything the scoring model needs to know about what this sailor wants."""

    var weights: Weights
    var wind_band_kn: Band
    var temp_band_c: Band
    var chop_sensitivity: Float64
    var gust_limit_kn: Float64


@fieldwise_init
struct Accessibility(Copyable, Movable):
    """Static, non-weather inputs to the accessibility component.

    Each sub-factor carries a `_known` flag. Milestone 1 uses an explicit flag rather
    than `Optional[Float64]` for one reason worth understanding: a flag keeps the
    struct a flat, fixed-size block of plain floats and bools, which is exactly what
    the SIMD work in milestone 8 needs. `Optional` would be perfectly correct and
    slightly nicer to read — and it is the right choice on the Python side, where it
    is used.

    An unknown sub-factor is dropped from the weighted average, never imputed as
    zero (FR-P-03): "we don't know whether there is a ramp" and "there is no ramp"
    are different facts.
    """

    var launch: Float64
    var launch_known: Bool
    var parking: Float64
    var parking_known: Bool
    var drive: Float64
    var drive_known: Bool
    var services: Float64
    var services_known: Bool


fn accessibility_unknown() -> Accessibility:
    """Nothing is known — the honest default before any facility data is ingested."""
    return Accessibility(0.0, False, 0.0, False, 0.0, False, 0.0, False)


@fieldwise_init
struct ScoreResult(Copyable, Movable):
    var total: Float64
    var confidence: Float64
    var raws: List[Float64]
    var known: List[Bool]
    var points: List[Float64]
    var max_points: List[Float64]
    var wind: WindStats


# --- individual components -------------------------------------------------


fn score_wind_quality(hours: List[HourlyWeather], band: Band) -> Float64:
    """Half from the window mean, half from how much of the window sits in the band.

    A day averaging 12 kn because it blew 4 in the morning and 20 in the afternoon
    is not the same day as a steady 12, and a mean-only score cannot tell them apart.
    """
    var n = len(hours)
    var speeds = List[Float64]()
    var per_hour_sum: Float64 = 0.0
    for i in range(n):
        var v = hours[i].wind_kn
        speeds.append(v)
        per_hour_sum += trapezoid(v, band.a, band.b, band.c, band.d)

    var from_mean = trapezoid(mean(speeds), band.a, band.b, band.c, band.d)
    var per_hour = per_hour_sum / Float64(n)
    return W_MEAN_SHARE * from_mean + (1.0 - W_MEAN_SHARE) * per_hour


fn score_wind_stability(stats: WindStats) -> Float64:
    var steadiness = clamp01(1.0 - stats.cv / CV_MAX)
    var gustiness = gust_excess_score(stats.gust_factor)
    return STAB_CV_SHARE * steadiness + (1.0 - STAB_CV_SHARE) * gustiness


fn score_weather(hours: List[HourlyWeather]) -> Float64:
    var n = len(hours)
    var storm_max = hours[0].storm_prob
    var vis_min = hours[0].visibility_m
    var cloud_sum: Float64 = 0.0
    for i in range(n):
        if hours[i].storm_prob > storm_max:
            storm_max = hours[i].storm_prob
        if hours[i].visibility_m < vis_min:
            vis_min = hours[i].visibility_m
        cloud_sum += hours[i].cloud_frac

    var cloud_mean = cloud_sum / Float64(n)
    var vis_score = clamp01((vis_min - VIS_BAD_M) / (VIS_GOOD_M - VIS_BAD_M))
    return (
        W_STORM * (1.0 - clamp01(storm_max))
        + W_VIS * vis_score
        + W_CLOUD * (1.0 - CLOUD_PENALTY * clamp01(cloud_mean))
    )


fn score_rain(hours: List[HourlyWeather]) -> Float64:
    var n = len(hours)
    var total_mm: Float64 = 0.0
    var prob_max = hours[0].precip_prob
    for i in range(n):
        total_mm += hours[i].precip_mm
        if hours[i].precip_prob > prob_max:
            prob_max = hours[i].precip_prob

    return clamp01(
        1.0
        - RAIN_AMOUNT_W * (total_mm / RAIN_REF_MM)
        - RAIN_PROB_W * clamp01(prob_max)
    )


fn score_temperature(hours: List[HourlyWeather], band: Band) -> Float64:
    var temps = List[Float64]()
    for i in range(len(hours)):
        temps.append(hours[i].temp_c)
    return trapezoid(mean(temps), band.a, band.b, band.c, band.d)


fn score_water_conditions(stats: WindStats, chop_sensitivity: Float64) -> Float64:
    """ESTIMATED, and it must be labelled as such wherever it is shown.

    v1 proxies surface chop from mean wind speed alone. A real model would use wind
    direction, the spot's exposed sectors and the fetch length; that is roadmap item
    M8+. Until then the honest label is "estimated from wind speed", not a wave height.
    """
    var chop = clamp01((stats.mean_kn - CHOP_ONSET_KN) / (CHOP_FULL_KN - CHOP_ONSET_KN))
    return clamp01(1.0 - chop * chop_sensitivity)


fn score_accessibility(access: Accessibility) -> (Float64, Bool, Float64):
    """Return (raw, known, confidence).

    Sub-factors that are unknown drop out of both numerator and denominator; the
    confidence reports how much of the intended weight was actually available.
    """
    var total_weight = (
        ACCESS_W_LAUNCH + ACCESS_W_PARKING + ACCESS_W_DRIVE + ACCESS_W_SERVICES
    )
    var weight_sum: Float64 = 0.0
    var acc: Float64 = 0.0

    if access.launch_known:
        weight_sum += ACCESS_W_LAUNCH
        acc += clamp01(access.launch) * ACCESS_W_LAUNCH
    if access.parking_known:
        weight_sum += ACCESS_W_PARKING
        acc += clamp01(access.parking) * ACCESS_W_PARKING
    if access.drive_known:
        weight_sum += ACCESS_W_DRIVE
        acc += clamp01(access.drive) * ACCESS_W_DRIVE
    if access.services_known:
        weight_sum += ACCESS_W_SERVICES
        acc += clamp01(access.services) * ACCESS_W_SERVICES

    if weight_sum == 0.0:
        return (0.0, False, 0.0)
    return (acc / weight_sum, True, weight_sum / total_weight)


# --- aggregation -----------------------------------------------------------


fn sailing_score(
    hours: List[HourlyWeather], profile: SailingProfile, access: Accessibility
) raises -> ScoreResult:
    """Compute the Sailing Score in [0, 100] for a window at one spot.

    Aggregation normalises by the sum of the weights of the components that were
    actually computable. Two properties fall out for free: a user-edited weight set
    that does not sum to 1 is still valid (FR-S-05), and a missing component shifts
    its weight onto the others rather than silently scoring zero (FR-P-03).
    """
    var n = len(hours)
    if n == 0:
        raise Error("sailing_score requires at least one hour of forecast")

    var stats = compute_wind_stats(hours)
    var access_result = score_accessibility(access)

    var raws = List[Float64]()
    var known = List[Bool]()
    var confidences = List[Float64]()

    raws.append(score_wind_quality(hours, profile.wind_band_kn))
    raws.append(score_wind_stability(stats))
    raws.append(score_weather(hours))
    raws.append(score_rain(hours))
    raws.append(score_temperature(hours, profile.temp_band_c))
    raws.append(score_water_conditions(stats, profile.chop_sensitivity))
    raws.append(access_result[0])

    for _ in range(N_COMPONENTS - 1):
        known.append(True)
        confidences.append(1.0)
    known.append(access_result[1])
    confidences.append(access_result[2])

    var available_weight: Float64 = 0.0
    var weighted_sum: Float64 = 0.0
    var confidence_sum: Float64 = 0.0
    for i in range(N_COMPONENTS):
        var w = profile.weights.get(i)
        confidence_sum += w * confidences[i]
        if known[i]:
            available_weight += w
            weighted_sum += w * raws[i]

    if available_weight <= 0.0:
        raise Error("no component could be computed")

    var total = 100.0 * weighted_sum / available_weight
    var confidence = confidence_sum / profile.weights.total()

    var points = List[Float64]()
    var max_points = List[Float64]()
    for i in range(N_COMPONENTS):
        var w = profile.weights.get(i)
        max_points.append(100.0 * w / available_weight)
        if known[i]:
            points.append(100.0 * w * raws[i] / available_weight)
        else:
            points.append(0.0)

    return ScoreResult(total, confidence, raws, known, points, max_points, stats)
