"""Normalised weather records and wind statistics.

Mirrors python/src/sailwise_ref/weather.py.

LEARNING NOTE — why `struct` and not `class`
    `HourlyWeather` is a *value*: nine numbers that travel together. Declaring it a
    struct means the layout is fixed at compile time, the fields sit inline in
    memory (no pointer chasing, no per-field boxing, no reference counting), and a
    `List[HourlyWeather]` is one contiguous block of memory.

    The equivalent Python object carries a `__dict__`, and a Python list of them is
    an array of pointers to objects scattered across the heap. That difference is
    the whole performance story, and it is also why struct-of-arrays (see
    ranking.mojo, milestone 3) beats array-of-structs once we start vectorising:
    SIMD wants nine separate contiguous lanes, not nine interleaved ones.
"""

from std.math import sqrt

from .units import clamp01, least_squares_slope, mean, stdev_population

# --- constants (mirror python/src/sailwise_ref/constants.py) ----------------

alias MEAN_WIND_FLOOR_KN: Float64 = 1.0
alias CV_MAX: Float64 = 0.60
alias GUST_EXCESS_MAX: Float64 = 0.80
alias TREND_SLOPE_KN_PER_H: Float64 = 0.5

# Wind trend codes. Integers rather than strings: the compute core never formats
# text, and an Int comparison is free. The Python layer maps these back to names.
alias TREND_STEADY: Int = 0
alias TREND_RISING: Int = 1
alias TREND_EASING: Int = 2
alias TREND_RISING_THEN_EASING: Int = 3
alias TREND_EASING_THEN_RISING: Int = 4


@fieldwise_init
struct HourlyWeather(Copyable, Movable):
    """One hour of normalised forecast at one location.

    Wind in knots, direction in meteorological degrees (where the wind comes FROM),
    temperature in Celsius, precipitation in mm for the hour, probabilities and
    fractions in [0, 1], visibility in metres.
    """

    var hour: Int
    var wind_kn: Float64
    var gust_kn: Float64
    var wind_dir_deg: Float64
    var temp_c: Float64
    var precip_mm: Float64
    var precip_prob: Float64
    var cloud_frac: Float64
    var visibility_m: Float64
    var storm_prob: Float64


fn fair_hour(hour: Int, wind_kn: Float64, gust_kn: Float64) -> HourlyWeather:
    """A fair-weather hour: convenient for tests, explicit about its defaults."""
    return HourlyWeather(
        hour, wind_kn, gust_kn, 0.0, 20.0, 0.0, 0.0, 0.0, 10000.0, 0.0
    )


@fieldwise_init
struct WindStats(Copyable, Movable):
    var mean_kn: Float64
    var max_kn: Float64
    var min_kn: Float64
    var gust_max_kn: Float64
    var gust_mean_kn: Float64
    var stdev_kn: Float64
    var cv: Float64
    var gust_factor: Float64
    var consistency: Float64
    var slope_kn_per_h: Float64
    var trend: Int


fn compute_wind_stats(hours: List[HourlyWeather]) raises -> WindStats:
    """Descriptive statistics for the wind over a scoring window.

    The MEAN_WIND_FLOOR_KN guard is the interesting line. With a near-calm forecast
    the coefficient of variation explodes and the gust factor divides by ~0. Rather
    than emit a NaN that would silently poison every downstream number, the
    statistics fall back to neutral values. In Python the same bug would surface as
    a `ZeroDivisionError` or a `nan` propagating quietly through the score; here it
    would be a `nan` too, because IEEE-754 is IEEE-754 in any language. Fast
    arithmetic does not save you from bad arithmetic.
    """
    var n = len(hours)
    if n == 0:
        raise Error("compute_wind_stats requires at least one hour")

    var speeds = List[Float64]()
    var gusts = List[Float64]()
    for i in range(n):
        speeds.append(hours[i].wind_kn)
        gusts.append(hours[i].gust_kn)

    var m = mean(speeds)
    var sd = stdev_population(speeds)
    var gm = mean(gusts)

    var max_kn = speeds[0]
    var min_kn = speeds[0]
    var gust_max = gusts[0]
    for i in range(1, n):
        if speeds[i] > max_kn:
            max_kn = speeds[i]
        if speeds[i] < min_kn:
            min_kn = speeds[i]
        if gusts[i] > gust_max:
            gust_max = gusts[i]

    var cv: Float64 = 1.0
    var gust_factor: Float64 = 1.0
    if m >= MEAN_WIND_FLOOR_KN:
        cv = sd / m
        gust_factor = gm / m

    var consistency = clamp01(1.0 - cv / CV_MAX)
    var slope = least_squares_slope(speeds)

    return WindStats(
        m,
        max_kn,
        min_kn,
        gust_max,
        gm,
        sd,
        cv,
        gust_factor,
        consistency,
        slope,
        classify_trend(speeds, slope),
    )


fn classify_trend(speeds: List[Float64], slope: Float64) -> Int:
    """Classify the shape of the day.

    A thermal lake breeze builds through the morning and dies in the late afternoon,
    so its overall slope is ~0 and a single-slope classifier would call the most
    characteristic day on Lake Como "steady". Splitting the window in half catches
    it — cheap, and much more useful to a sailor.
    """
    var n = len(speeds)
    if n >= 4:
        var half = n // 2
        var first = List[Float64]()
        var second = List[Float64]()
        for i in range(half):
            first.append(speeds[i])
        for i in range(half, n):
            second.append(speeds[i])

        var s1 = least_squares_slope(first)
        var s2 = least_squares_slope(second)
        if s1 >= TREND_SLOPE_KN_PER_H and s2 <= -TREND_SLOPE_KN_PER_H:
            return TREND_RISING_THEN_EASING
        if s1 <= -TREND_SLOPE_KN_PER_H and s2 >= TREND_SLOPE_KN_PER_H:
            return TREND_EASING_THEN_RISING

    if slope >= TREND_SLOPE_KN_PER_H:
        return TREND_RISING
    if slope <= -TREND_SLOPE_KN_PER_H:
        return TREND_EASING
    return TREND_STEADY


fn gust_excess_score(gust_factor: Float64) -> Float64:
    """Sub-score in [0, 1] for gustiness: 1.0 when gusts equal the mean wind."""
    return clamp01(1.0 - (gust_factor - 1.0) / GUST_EXCESS_MAX)
