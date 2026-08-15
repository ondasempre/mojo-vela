"""Sailing profiles: weights and preference bands.

Mirrors python/src/sailwise_ref/profiles.py. Values must match exactly — they are
part of the cross-language golden test.

These defaults are a starting hypothesis, not physics (docs/05-algorithms.md). In
the running system they arrive as configuration; here they are compile-time
constants so that Milestone 1 has something concrete to score with.

LEARNING NOTE — `alias` vs `var`
    Each function below builds a struct at runtime. The numbers inside are literals,
    so the compiler can fold the whole construction into a constant. Writing them as
    `alias` at module level would force the same, but functions keep the door open
    for loading profiles from configuration later without changing call sites.
"""

from .score import Band, SailingProfile, Weights

alias PROFILE_RELAX: Int = 0
alias PROFILE_CRUISING: Int = 1
alias PROFILE_TRAINING: Int = 2
alias PROFILE_RACING: Int = 3
alias PROFILE_FAMILY: Int = 4
alias PROFILE_SPORT: Int = 5


fn profile_relax() -> SailingProfile:
    return SailingProfile(
        Weights(0.22, 0.22, 0.16, 0.10, 0.14, 0.11, 0.05),
        Band(3.0, 6.0, 12.0, 18.0),
        Band(5.0, 18.0, 30.0, 38.0),
        0.80,
        18.0,
    )


fn profile_cruising() -> SailingProfile:
    return SailingProfile(
        Weights(0.30, 0.20, 0.20, 0.05, 0.10, 0.05, 0.10),
        Band(4.0, 8.0, 16.0, 22.0),
        Band(5.0, 18.0, 30.0, 38.0),
        0.60,
        22.0,
    )


fn profile_training() -> SailingProfile:
    return SailingProfile(
        Weights(0.34, 0.28, 0.14, 0.06, 0.06, 0.06, 0.06),
        Band(5.0, 10.0, 18.0, 25.0),
        Band(5.0, 16.0, 30.0, 38.0),
        0.35,
        26.0,
    )


fn profile_racing() -> SailingProfile:
    return SailingProfile(
        Weights(0.38, 0.30, 0.12, 0.04, 0.03, 0.07, 0.06),
        Band(5.0, 10.0, 20.0, 30.0),
        Band(0.0, 12.0, 30.0, 40.0),
        0.20,
        30.0,
    )


fn profile_family() -> SailingProfile:
    return SailingProfile(
        Weights(0.18, 0.22, 0.18, 0.12, 0.14, 0.10, 0.06),
        Band(2.0, 5.0, 10.0, 15.0),
        Band(12.0, 20.0, 30.0, 36.0),
        0.90,
        14.0,
    )


fn profile_sport() -> SailingProfile:
    return SailingProfile(
        Weights(0.36, 0.16, 0.14, 0.06, 0.06, 0.12, 0.10),
        Band(8.0, 14.0, 24.0, 33.0),
        Band(5.0, 16.0, 30.0, 38.0),
        0.30,
        32.0,
    )


fn get_profile(id: Int) -> SailingProfile:
    if id == PROFILE_RELAX:
        return profile_relax()
    if id == PROFILE_TRAINING:
        return profile_training()
    if id == PROFILE_RACING:
        return profile_racing()
    if id == PROFILE_FAMILY:
        return profile_family()
    if id == PROFILE_SPORT:
        return profile_sport()
    return profile_cruising()
