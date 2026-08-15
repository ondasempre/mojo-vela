"""Golden values for the cross-language equivalence tests (NFR-C-01).

GENERATED FILE — do not edit by hand.
Regenerate with:  python3 scripts/gen_golden.py

Source of truth: the Python reference implementation in python/src/sailwise_ref.
Model version: 1.0.0
"""

# Wind statistics over the synthetic Dervio day.
alias GOLDEN_WIND_MEAN_KN: Float64 = 10.222222222222221
alias GOLDEN_WIND_MAX_KN: Float64 = 15.0
alias GOLDEN_WIND_MIN_KN: Float64 = 5.0
alias GOLDEN_WIND_GUST_MAX_KN: Float64 = 17.8
alias GOLDEN_WIND_GUST_MEAN_KN: Float64 = 12.922222222222222
alias GOLDEN_WIND_STDEV_KN: Float64 = 3.292340531117567
alias GOLDEN_WIND_CV: Float64 = 0.32207679108758813
alias GOLDEN_WIND_GUST_FACTOR: Float64 = 1.2641304347826088
alias GOLDEN_WIND_CONSISTENCY: Float64 = 0.46320534818735304
alias GOLDEN_WIND_SLOPE_KN_PER_H: Float64 = 0.4666666666666667

# Total score per profile.
alias GOLDEN_TOTAL_RELAX: Float64 = 85.03078545666814
alias GOLDEN_TOTAL_CRUISING: Float64 = 84.4820294412098
alias GOLDEN_TOTAL_TRAINING: Float64 = 79.40498981835923
alias GOLDEN_TOTAL_RACING: Float64 = 78.26497136060274
alias GOLDEN_TOTAL_FAMILY: Float64 = 82.80731469517485
alias GOLDEN_TOTAL_SPORT: Float64 = 65.87821614556043

# Component raw sub-scores for CRUISING (the reference profile).
alias GOLDEN_CRUISING_WIND_QUALITY: Float64 = 0.9305555555555556
alias GOLDEN_CRUISING_WIND_STABILITY: Float64 = 0.5458579915211075
alias GOLDEN_CRUISING_WEATHER: Float64 = 0.875
alias GOLDEN_CRUISING_RAIN: Float64 = 0.94
alias GOLDEN_CRUISING_TEMPERATURE: Float64 = 1.0
alias GOLDEN_CRUISING_WATER_CONDITIONS: Float64 = 1.0
# accessibility: UNKNOWN (excluded from aggregation)

#: Maximum permitted absolute difference between the two implementations.
alias GOLDEN_TOLERANCE: Float64 = 1e-9
