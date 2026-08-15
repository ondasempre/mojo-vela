"""Named constants for the SailWise scoring model.

Every constant used by the scoring model lives here. No magic numbers anywhere else
(NFR-C-03). The Mojo implementation mirrors this file in ``mojo/src/sailwise/units.mojo``
and ``score.mojo``; the two must stay in sync and CI proves it (NFR-C-01).

Reference: docs/05-algorithms.md
"""

from __future__ import annotations

#: Version of the scoring model. Stored alongside every computed score so that
#: historical scores stay interpretable after the model changes.
SCORE_MODEL_VERSION = "1.0.0"

# --- wind statistics -------------------------------------------------------

#: Below this mean wind speed, the coefficient of variation and the gust factor are
#: numerically meaningless (and the division is unsafe), so neutral values are used.
MEAN_WIND_FLOOR_KN = 1.0

#: A series whose standard deviation reaches this fraction of its mean scores 0 for steadiness.
CV_MAX = 0.60

#: A mean gust factor of 1 + this value scores 0 for gust steadiness.
GUST_EXCESS_MAX = 0.80

#: Hourly slope (kn/h) above which the wind is classified as rising / easing.
TREND_SLOPE_KN_PER_H = 0.5

# --- component weights inside components -----------------------------------

#: Share of `wind_quality` taken from the window mean; the rest comes from the
#: per-hour membership average.
W_MEAN_SHARE = 0.5

#: Share of `wind_stability` taken from the coefficient of variation; the rest from gustiness.
STAB_CV_SHARE = 0.6

# --- weather ---------------------------------------------------------------

VIS_BAD_M = 1_000.0
VIS_GOOD_M = 10_000.0
CLOUD_PENALTY = 0.6

W_STORM = 0.50
W_VIS = 0.25
W_CLOUD = 0.25

# --- rain ------------------------------------------------------------------

RAIN_AMOUNT_W = 0.6
RAIN_PROB_W = 0.4
#: Total precipitation over the window (mm) at which the rain component reaches 0.
RAIN_REF_MM = 5.0

# --- lake / sea surface ----------------------------------------------------

CHOP_ONSET_KN = 12.0
CHOP_FULL_KN = 30.0

# --- accessibility ---------------------------------------------------------

ACCESS_W_LAUNCH = 0.40
ACCESS_W_PARKING = 0.25
ACCESS_W_DRIVE = 0.20
ACCESS_W_SERVICES = 0.15

#: Number of nearby services at which the services sub-factor saturates.
SERVICE_REF = 4.0

# --- recommendation --------------------------------------------------------

#: Minimum score for `is_recommended`. A CRITICAL warning overrides this regardless (FR-Z-02).
RECOMMEND_THRESHOLD = 60.0

# --- personalisation (M9, defined here so the model is complete) ------------

PRIOR_WEIGHT = 3.0
PRIOR_AFFINITY = 0.55

# --- ranking (M3) ----------------------------------------------------------

RANK_W_SAIL = 0.65
RANK_W_ACCESS = 0.20
RANK_W_AFFIN = 0.15
