"""Shared numeric primitives.

Mirrors python/src/sailwise_ref/units.py. Every function here is a pure `fn` over
`Float64`: no allocation, no error paths, no I/O. That is deliberate — these are the
functions that will later be rewritten with SIMD (learning level 6), and a pure
scalar function with a known signature is the easiest thing in the world to
vectorise and to verify afterwards.

LEARNING NOTE
    `fn` (rather than `def`) means: arguments are typed, the compiler knows every
    type at compile time, and the function cannot raise unless it says `raises`.
    That is what lets Mojo emit a handful of machine instructions here instead of
    the CPython interpreter's dictionary lookups and boxed floats.
"""

from std.math import sqrt

# --- unit conversions (canonical units: knots, NM, degC, mm, hPa, m) ---------

alias MS_TO_KN: Float64 = 1.943844492440605
alias KMH_TO_KN: Float64 = 0.539956803455724
alias NM_TO_KM: Float64 = 1.852


fn ms_to_kn(v: Float64) -> Float64:
    return v * MS_TO_KN


fn kmh_to_kn(v: Float64) -> Float64:
    return v * KMH_TO_KN


fn nm_to_km(v: Float64) -> Float64:
    return v * NM_TO_KM


fn km_to_nm(v: Float64) -> Float64:
    return v / NM_TO_KM


# --- model primitives -------------------------------------------------------


fn clamp01(x: Float64) -> Float64:
    """Clamp to [0, 1]. Every sub-score in the model passes through this."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


fn trapezoid(x: Float64, a: Float64, b: Float64, c: Float64, d: Float64) -> Float64:
    """Trapezoidal membership of `x` in the band (a, b, c, d), with a <= b <= c <= d.

    Zero outside [a, d], linear up over [a, b], one over [b, c], linear down over
    [c, d]. The ordering of the tests below guarantees the denominators are never
    zero: we only reach `(x - a) / (b - a)` when a < x < b, which implies b > a.
    """
    if x <= a or x >= d:
        return 0.0
    if x < b:
        return (x - a) / (b - a)
    if x <= c:
        return 1.0
    return (d - x) / (d - c)


fn mean(values: List[Float64]) -> Float64:
    var n = len(values)
    if n == 0:
        return 0.0
    var total: Float64 = 0.0
    for i in range(n):
        total += values[i]
    return total / Float64(n)


fn stdev_population(values: List[Float64]) -> Float64:
    """Population standard deviation (divides by n).

    The scoring window is the whole population of hours being scored, not a sample
    drawn from a larger one, so n is the correct divisor. This matters: using n-1
    here would silently break the cross-language equivalence test.
    """
    var n = len(values)
    if n == 0:
        return 0.0
    var m = mean(values)
    var acc: Float64 = 0.0
    for i in range(n):
        var d = values[i] - m
        acc += d * d
    return sqrt(acc / Float64(n))


fn least_squares_slope(values: List[Float64]) -> Float64:
    """Slope of the best-fit line at unit x spacing (kn per hour)."""
    var n = len(values)
    if n < 2:
        return 0.0
    var mean_x = Float64(n - 1) / 2.0
    var mean_y = mean(values)
    var num: Float64 = 0.0
    var den: Float64 = 0.0
    for i in range(n):
        var dx = Float64(i) - mean_x
        num += dx * (values[i] - mean_y)
        den += dx * dx
    if den == 0.0:
        return 0.0
    return num / den
