"""Unit conversions and the shared mathematical primitives.

Canonical units inside SailWise (FR-W-03): knots, degrees, Celsius, millimetres,
hectopascals, metres, nautical miles. Conversion happens here and in provider
adapters -- never inside the scoring engine.
"""

from __future__ import annotations

MS_TO_KN = 1.943_844_492_440_605
KMH_TO_KN = 0.539_956_803_455_724
KN_TO_MS = 1.0 / MS_TO_KN
NM_TO_KM = 1.852


def ms_to_kn(v: float) -> float:
    return v * MS_TO_KN


def kmh_to_kn(v: float) -> float:
    return v * KMH_TO_KN


def kn_to_ms(v: float) -> float:
    return v * KN_TO_MS


def nm_to_km(v: float) -> float:
    return v * NM_TO_KM


def km_to_nm(v: float) -> float:
    return v / NM_TO_KM


def clamp01(x: float) -> float:
    """Clamp to the unit interval. Every sub-score in the model is a clamp01 output."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership of ``x`` in the band ``(a, b, c, d)``.

    Returns 0 outside [a, d], ramps linearly up over [a, b], is 1 over [b, c] and
    ramps down over [c, d]. Degenerate edges (a == b or c == d) are handled without
    dividing by zero.

    This is the single primitive behind every "preferred range" in the model: wind
    band, temperature band. It encodes exactly the four numbers a sailor can state in
    words, and it is piecewise linear -- cheap, and explainable when tuning.

    Requires a <= b <= c <= d.
    """
    if x <= a or x >= d:
        return 0.0
    if x < b:
        # a < x < b, and b > a is guaranteed because x < b and x > a.
        return (x - a) / (b - a)
    if x <= c:
        return 1.0
    # c < x < d, and d > c is guaranteed because x > c and x < d.
    return (d - x) / (d - c)


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def stdev_population(values: list[float]) -> float:
    """Population standard deviation (divides by n, not n-1).

    The window is the whole population of hours we are scoring, not a sample drawn
    from a larger one, so n is correct here.
    """
    n = len(values)
    if n == 0:
        return 0.0
    m = sum(values) / n
    return (sum((v - m) ** 2 for v in values) / n) ** 0.5


def least_squares_slope(values: list[float]) -> float:
    """Slope of the best-fit line through ``values`` at unit x-spacing (per hour)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0.0:
        return 0.0
    return num / den
