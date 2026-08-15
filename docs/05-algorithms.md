# 19–22. Sailing Score, Ranking, Route Planning, Personalisation

This document is the specification. `python/src/sailwise_ref/` implements it and is the oracle;
`mojo/src/sailwise/` must reproduce it within 1e-9 (NFR-C-01). Change the document first.

Every constant below is **named** and lives in one place per implementation. No magic numbers.

## Shared primitives

**`clamp01(x)`** = `min(1.0, max(0.0, x))`.

**`trapezoid(x; a, b, c, d)`** — the membership function used for every "band" preference
(`a ≤ b ≤ c ≤ d`):

```
        1.0 ┤        ┌──────────┐
            │       ╱            ╲
        0.0 ┼──────┘              └──────
            a      b            c        d
```

```
trapezoid(x) = 0                    if x <= a or x >= d
             = (x - a) / (b - a)    if a < x < b        (0 when b == a)
             = 1                    if b <= x <= c
             = (d - x) / (d - c)    if c < x < d        (0 when d == c)
```

Why a trapezoid and not a Gaussian or a step: it encodes exactly the four numbers a sailor can state
in words — "below 4 kn it's pointless, 8 to 16 is what I like, above 22 I'm not going out" — and it is
piecewise-linear, so it is cheap, explainable, and its derivative is intuitive when tuning.

## 19. Sailing Score

### Inputs

For a spot, a contiguous set of `n` hourly forecast records inside the user's availability window,
plus the spot's static facilities, plus the scoring profile.

Per hour: `wind_kn`, `gust_kn`, `wind_dir_deg`, `temp_c`, `precip_mm`, `precip_prob`, `cloud_frac`,
`visibility_m`, `storm_prob`.

### Wind statistics (FR-S-09)

```
mean      = Σ v_i / n
max       = max v_i
gust_max  = max g_i
stdev     = sqrt( Σ (v_i - mean)² / n )                   (population, n not n-1)
cv        = stdev / mean                  if mean >= MEAN_WIND_FLOOR else 1.0
gust_fact = (Σ g_i / n) / mean            if mean >= MEAN_WIND_FLOOR else 1.0
consistency = clamp01(1 - cv / CV_MAX)
trend       = sign-classified from a least-squares slope over the hourly series
```

`MEAN_WIND_FLOOR = 1.0 kn` guards the division; below it, wind quality is already ~0 and stability is
meaningless, so neutral values are used rather than a NaN.

### The seven components

Each returns a raw sub-score in `[0, 1]`.

**1. `wind_quality`** — half from the window's mean, half from how much of the window actually sits
in the band. A day averaging 12 kn because it blew 4 then 20 is not the same day as a steady 12.

```
band = (lo_cut, lo_ideal, hi_ideal, hi_cut)          from the profile, overridable per user
wind_quality = W_MEAN_SHARE * trapezoid(mean; band)
             + (1 - W_MEAN_SHARE) * (Σ trapezoid(v_i; band) / n)
W_MEAN_SHARE = 0.5
```

**2. `wind_stability`**

```
wind_stability = STAB_CV_SHARE   * clamp01(1 - cv / CV_MAX)
               + (1 - STAB_CV_SHARE) * clamp01(1 - (gust_fact - 1) / GUST_EXCESS_MAX)
STAB_CV_SHARE = 0.6 ; CV_MAX = 0.60 ; GUST_EXCESS_MAX = 0.80
```

`CV_MAX = 0.60` means a series whose standard deviation reaches 60 % of its mean scores zero for
steadiness. `GUST_EXCESS_MAX = 0.80` means a mean gust factor of 1.8 scores zero.

**3. `weather`**

```
vis_score = clamp01( (vis_min - VIS_BAD_M) / (VIS_GOOD_M - VIS_BAD_M) )
weather   = 0.50 * (1 - storm_prob_max)
          + 0.25 * vis_score
          + 0.25 * (1 - CLOUD_PENALTY * cloud_frac_mean)
VIS_BAD_M = 1000 ; VIS_GOOD_M = 10000 ; CLOUD_PENALTY = 0.6
```

Cloud is penalised gently and deliberately: overcast is unpleasant, not unsailable.

**4. `rain`**

```
rain = clamp01( 1 - RAIN_AMOUNT_W * (precip_total_mm / RAIN_REF_MM) - RAIN_PROB_W * precip_prob_max )
RAIN_AMOUNT_W = 0.6 ; RAIN_PROB_W = 0.4 ; RAIN_REF_MM = 5.0
```

**5. `temperature`** — `trapezoid(temp_mean; temp_band)` from the profile.

**6. `water_conditions`** — `ESTIMATED` in v1, and labelled as such in the UI.

```
chop = clamp01( (mean - CHOP_ONSET_KN) / (CHOP_FULL_KN - CHOP_ONSET_KN) )
water_conditions = clamp01( 1 - chop * chop_sensitivity )
CHOP_ONSET_KN = 12.0 ; CHOP_FULL_KN = 30.0 ; chop_sensitivity from the profile
```

When a provider supplies wave height, the wave-based form replaces it and provenance becomes
`FORECAST`. A lake fetch model (wind direction × exposed sector × fetch length) is a candidate for
M8+; until it exists, the honest label is "estimated from wind speed".

**7. `accessibility`**

```
accessibility = Σ (w_k * s_k) / Σ w_k   over the AVAILABLE sub-factors only
  launch   w=0.40   1.0 public ramp suitable for the boat, 0.6 beach launch, 0.0 none
  parking  w=0.25   from the Parking Score (below)
  drive    w=0.20   clamp01(1 - drive_minutes / max_drive_minutes)
  services w=0.15   clamp01(service_count / SERVICE_REF), SERVICE_REF = 4
```

Sub-factors whose data is `UNKNOWN` are **dropped from both numerator and denominator** and lower the
result's confidence (FR-P-03). They are never imputed.

### Aggregation

```
available   = the components whose inputs were not UNKNOWN
score_0_100 = 100 * Σ_available (weight_j * component_j) / Σ_available weight_j
confidence  = Σ_all (weight_j * confidence_j) / Σ_all weight_j     (confidence_j ∈ [0, 1])
```

Two properties fall out of normalising by the *available* weight rather than assuming the weights sum
to 1:

- a user-edited weight set that does not sum to 1 is still valid (FR-S-05) — scaling every weight by
  the same factor leaves the score unchanged, which is a property worth asserting in a test;
- a component whose data is missing shifts its weight onto the others instead of scoring zero
  (FR-P-03), and the loss shows up in `confidence` rather than in the score. "We don't know whether
  there is a ramp" must not be punished like "there is no ramp".

### Profile weight table (defaults, configurable — FR-S-03)

| Profile | wind | stability | weather | rain | temp | water | access |
|---|---|---|---|---|---|---|---|
| RELAX | 0.22 | 0.22 | 0.16 | 0.10 | 0.14 | 0.11 | 0.05 |
| CRUISING | 0.30 | 0.20 | 0.20 | 0.05 | 0.10 | 0.05 | 0.10 |
| TRAINING | 0.34 | 0.28 | 0.14 | 0.06 | 0.06 | 0.06 | 0.06 |
| RACING | 0.38 | 0.30 | 0.12 | 0.04 | 0.03 | 0.07 | 0.06 |
| FAMILY | 0.18 | 0.22 | 0.18 | 0.12 | 0.14 | 0.10 | 0.06 |
| SPORT | 0.36 | 0.16 | 0.14 | 0.06 | 0.06 | 0.12 | 0.10 |

CRUISING reproduces the weighting given in the project brief.

| Profile | wind band (kn) `a,b,c,d` | temp band (°C) | chop sens. |
|---|---|---|---|
| RELAX | 3, 6, 12, 18 | 5, 18, 30, 38 | 0.80 |
| CRUISING | 4, 8, 16, 22 | 5, 18, 30, 38 | 0.60 |
| TRAINING | 5, 10, 18, 25 | 5, 16, 30, 38 | 0.35 |
| RACING | 5, 10, 20, 30 | 0, 12, 30, 40 | 0.20 |
| FAMILY | 2, 5, 10, 15 | 12, 20, 30, 36 | 0.90 |
| SPORT | 8, 14, 24, 33 | 5, 16, 30, 38 | 0.30 |

**These defaults are a starting hypothesis, not physics.** They are versioned (`score_model_version`)
and stored with every computed score so that historical scores remain interpretable after a change.

### Safety gates — a separate pipeline (FR-Z-01, FR-Z-02)

Gates read the same forecast but never touch the score. They emit warnings.

| Code | Condition | Severity |
|---|---|---|
| `INSUFFICIENT_WIND` | `mean < lo_cut` | INFO |
| `GUST_ABOVE_LIMIT` | `gust_max > gust_limit` | CAUTION |
| `GUST_FAR_ABOVE_LIMIT` | `gust_max > 1.3 × gust_limit` | CRITICAL |
| `WIND_ABOVE_RANGE` | `max > hi_cut` | CAUTION |
| `THUNDERSTORM_RISK` | `storm_prob_max ≥ 0.30` | CAUTION |
| `THUNDERSTORM_LIKELY` | `storm_prob_max ≥ 0.50` | CRITICAL |
| `VISIBILITY_REDUCED` | `vis_min < 3000 m` | CAUTION |
| `VISIBILITY_LOW` | `vis_min < 1000 m` | CRITICAL |
| `RAPID_WIND_INCREASE` | any `v_{i+1} - v_i ≥ 8 kn` | CAUTION |

`return_by` = the first hour triggering a CAUTION-or-worse gust/storm gate, minus
`SAFETY_MARGIN_MIN = 30` minutes.

`is_recommended = (score ≥ RECOMMEND_THRESHOLD) AND (no CRITICAL warning)`, with
`RECOMMEND_THRESHOLD = 60`. A CRITICAL warning is never outvoted by a high score.

### Best sailing window (FR-S-07)

Per-hour suitability, with a hard exclusion mask:

```
suitable_i = 0  if  g_i > gust_limit  or  storm_prob_i >= 0.5
h_i = 0.5 * trapezoid(v_i; band) + 0.3 * (1 - storm_prob_i) + 0.2 * (1 - clamp01(precip_i / 2.0))
```

Then: find the contiguous run of at least `D_min` hours, containing no excluded hour, maximising the
mean of `h_i`; ties broken by the earlier start. With prefix sums this is O(n·k) for all admissible
lengths and O(n) for a fixed length — small at n = 24, but it is the natural first SIMD exercise
(Learning Level 6) because it is a sliding reduction over a contiguous float array.

## 20. Ranking algorithm

**Stage 1 — hard filters** (cheap, before any scoring):
driving distance ≤ limit; required facilities present (e.g. `needs_ramp`); spot open/available;
user blacklist. A spot filtered here is reported with its reason, not silently dropped.

**Stage 2 — score** each survivor (above).

**Stage 3 — combine**:

```
rank_score = RANK_W_SAIL   * sailing_score          (0–100)
           + RANK_W_ACCESS * accessibility_score     (0–100)
           + RANK_W_AFFIN  * affinity * 100          (affinity 0–1)
RANK_W_SAIL = 0.65 ; RANK_W_ACCESS = 0.20 ; RANK_W_AFFIN = 0.15
```

**Stage 4 — top-k** by partial selection, not a full sort, once the candidate set is large.

**Stage 5 — explain**: for any pair (i, j), the explanation is the list of per-component contribution
deltas sorted by absolute magnitude — "Colico loses 4.1 points on wind stability and gains 1.2 on
accessibility" (FR-R-05). This falls out of storing contributions, which is why the score returns a
breakdown rather than a number.

Cold start (FR-R-04): with no history, `affinity` uses the prior alone, so ranking reduces to
`0.65·sailing + 0.20·access + 0.15·prior` — the prior is constant across spots and therefore does not
distort the ordering.

## 21. Route planning algorithm

**Stated bluntly: this produces an ESTIMATE for planning, not a navigational route.** No depth data,
no obstruction data, no traffic separation, no local regulation. The UI must say so wherever a route
appears (FR-Z-05, brief §8).

**Graph.** Nodes are waypoints (spots, headlands, bays) with verified coordinates; edges connect
waypoints with a line-of-water path validated against a coastline polygon. Edge weight is estimated
sailing time.

**Boat speed model — a simplified polar.** For true wind speed `TWS` and true wind angle `TWA`:

```
hull_speed_kn = HULL_COEFF * sqrt(LWL_m)                       HULL_COEFF = 2.43 (kn per √m)
angle_factor(TWA):  <30° → 0.00 (dead upwind: must tack)
                    30–45° → 0.55        45–60° → 0.75
                    60–110° → 1.00       110–150° → 0.90
                    150–180° → 0.70
boat_speed = min(hull_speed_kn, TWS * SPEED_RATIO * angle_factor(TWA))
SPEED_RATIO = 0.55   (a coarse, boat-class-dependent efficiency factor)
```

Upwind legs are traversed by tacking: the effective distance is `leg / cos(TACK_ANGLE)` with
`TACK_ANGLE = 45°`, i.e. ≈ 1.41 × the rhumb-line distance, at the 45° `angle_factor`.

**Along-route conditions.** Each leg is evaluated at its expected arrival hour, not at departure —
which is the whole point of doing this rather than reading a single forecast. Leg arrival times are
computed forward from the start, so leg *k*'s wind comes from hour `t0 + Σ durations`.

**Route score** = the mean of per-leg sailing scores weighted by leg duration, plus a penalty for any
leg whose estimated conditions trip a safety gate. A route containing a CRITICAL leg is not proposed.

**Confidence** is reported as LOW whenever any of: legs are estimated from straight lines rather than
a validated water path; the polar is a class default rather than a measured polar; the forecast is
more than 24 h out.

## 22. Personalisation engine

Three mechanisms, in increasing order of ambition. Only the first two are in the near roadmap.

**(a) Explicit preferences (M9).** The user's own bands override the profile defaults. Simple,
transparent, and by far the highest value per unit of complexity.

**(b) Affinity from history (M9).** Per (user, spot), with Bayesian shrinkage so that one lucky day
does not crown a spot:

```
affinity = (n * mean_rating_normalised + PRIOR_WEIGHT * PRIOR_AFFINITY) / (n + PRIOR_WEIGHT)
mean_rating_normalised = mean(user_rating) / 10
PRIOR_WEIGHT = 3.0 ; PRIOR_AFFINITY = 0.55
```

One 9/10 visit gives `(1·0.9 + 3·0.55)/4 = 0.64`, not 0.90 — the estimate earns its confidence.

**(c) Learned preferences (post-M10, opt-in).** Fit the user's wind band from the sessions they rated
highly: a weighted quantile of observed wind on 8+ rated outings. Output is a **proposal** the user
accepts or rejects (FR-L-05). No silent model updates, ever — a planner that quietly changes its mind
about what you like is a planner you stop trusting.

Anti-feedback-loop note: recommendations bias which spots get visited, which biases affinity, which
biases recommendations. Mitigations: cap the affinity term at 15 % of rank score (above); keep an
explicit "show me somewhere new" mode that zeroes the affinity term; log the counterfactual ranking
without affinity so drift is measurable.
