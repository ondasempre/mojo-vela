"""SailWise reference implementation.

Pure-Python, standard-library-only implementation of the SailWise compute model.

It serves three purposes at once:

1. it is the **specification made executable** (docs/05-algorithms.md);
2. it is the **oracle** the Mojo implementation is verified against (NFR-C-01);
3. it is the **runtime fallback** when the Mojo backend is unavailable (NFR-M-02).

It performs no I/O beyond loading local fixtures, and it has no third-party
dependencies, so it runs anywhere Python runs.
"""

from .constants import SCORE_MODEL_VERSION
from .profiles import COMPONENT_IDS, PROFILES, Band, ProfileId, SailingProfile, Weights, get_profile
from .score import AccessibilityInput, Component, ScoreResult, sailing_score
from .units import clamp01, trapezoid
from .weather import HourlyWeather, WindStats, wind_stats

__all__ = [
    "SCORE_MODEL_VERSION",
    "COMPONENT_IDS",
    "PROFILES",
    "Band",
    "ProfileId",
    "SailingProfile",
    "Weights",
    "get_profile",
    "AccessibilityInput",
    "Component",
    "ScoreResult",
    "sailing_score",
    "clamp01",
    "trapezoid",
    "HourlyWeather",
    "WindStats",
    "wind_stats",
]

__version__ = "0.1.0"
