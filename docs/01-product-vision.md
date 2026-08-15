# 1–5. Executive Summary, Vision, Personas, User Stories, Use Cases

## 1. Executive Summary

SailWise is an intelligent sailing planner. It answers one question well, and everything else is in
service of it:

> *"I want to go sailing today. Where should I go, when should I leave, and what will it be like?"*

Today a sailor answers that question by cross-referencing four or five apps — a forecast app, a map,
a parking search, a restaurant search, and their own memory of the last twenty outings. SailWise
merges those into a single ranked answer with a defensible explanation attached.

The system is deliberately **hybrid**: a Python service layer for orchestration, I/O and integrations,
and a Mojo compute core for the numerical work (scoring, ranking, window search, route evaluation).
The split is not decorative — [adr/0001](adr/0001-hybrid-python-mojo.md) sets the rule that a workload
only moves to Mojo once a benchmark shows it is worth moving.

There is a second, equally real goal: this project is the author's vehicle for learning Mojo deeply.
The architecture therefore exposes a genuine, growing computational kernel rather than a toy — the
ranking problem naturally scales from 5 spots to 5,000, which is exactly the shape of problem where
SIMD and parallelism stop being an academic exercise.

**Initial geographic scope:** Lake Como, starting from Dervio. **Designed scope:** any lake, then the
Mediterranean, then anywhere — which is why nothing in the data model hardcodes a body of water.

## 2. Product Vision

**Vision statement.** *For sailors who plan their own outings, SailWise turns raw forecast data into a
decision — where to sail, when to be on the water, and what to expect — while being explicit about
what it knows, what it estimates, and what it cannot tell you.*

**What SailWise is:**

- a decision-support tool for recreational and club sailors;
- a deterministic scoring engine with a transparent, configurable model;
- a personal logbook that feeds back into future recommendations;
- an aggregator that is honest about provenance and gaps.

**What SailWise is explicitly not:**

- a navigation instrument;
- a replacement for official forecasts, port authority notices or navigational warnings;
- a safety certification of any kind;
- a source of truth for commercial information (opening hours, prices) it did not verify.

**Design pillars.**

| Pillar | Consequence in the product |
|---|---|
| Answer first | The Home screen shows a recommendation before it shows data. |
| Explain always | Every score decomposes into named components on tap. |
| Provenance visible | Each figure shows source + timestamp + freshness state. |
| Safety separated | Warnings render in their own visual channel and cannot be scored away. |
| Personal over generic | Ranking is shaped by the user's own history and preferences. |
| Offline-tolerant | Stale cache is served with a visible "stale" marker rather than an error. |

## 3. Personas

**P1 — Flavio, the owner-operator (primary).** 45, owns a 7.5 m keelboat kept on a trailer near Lake
Como. Sails 20–30 days a year, mostly day trips, often deciding the same morning. Drives up to ~100 km.
Cares about: is there usable wind, can I launch and park, will I be back before the afternoon gusts.
Pain: checking five sources at 07:30 and still guessing. *Primary persona for MVP 1.*

**P2 — Giulia, the club racer.** 29, sails a dinghy at a club, trains on weekday evenings. Wants wind
*consistency* in a narrow band far more than she wants comfort. Cares about: gust factor, shifts, the
exact best two-hour window. Drives the need for scoring **profiles** (§5 of the brief).

**P3 — The Rossi family, casual cruisers.** Two adults, two children, charter or club boat, three
outings a summer. Cares about: light stable wind, no thunderstorm risk, a beach, lunch, easy parking.
Drives the FAMILY profile and the food/services layer.

**P4 — Marco, the visiting sailor.** Sails Lake Garda normally, visiting Como for a weekend, knows
nothing local. Has no history in the app. Drives the cold-start requirement: the system must be useful
with an empty profile.

**P5 — The maintainer (secondary, internal).** Runs the open-source project. Cares about reproducible
benchmarks, provider licensing hygiene, and not being on the hook for someone's bad day on the water.

## 4. User Stories

Grouped by epic. `[M1]`…`[M10]` map to the milestones in [10-roadmap.md](10-roadmap.md).

### Epic A — Conditions

- **A1** As a sailor, I want the hourly wind, gust and direction forecast for a spot, so that I can see
  how the day develops. `[M4]`
- **A2** As a sailor, I want a single 0–100 Sailing Score for a day at a spot, so that I get an
  instant verdict. `[M1 core / M4 end-to-end]`
- **A3** As a sailor, I want the score broken into named components, so that I can tell *why* it is 88
  and not 95. `[M1]`
- **A4** As a sailor, I want a recommended sailing window, so that I know when to be rigged and ready. `[M2]`
- **A5** As a sailor, I want to know when a number comes from cache and how old it is, so that I can
  judge whether to refresh. `[M5]`

### Epic B — Where to go

- **B1** As a sailor, I want spots ranked for today given my start point and driving limit, so that I
  can pick the best reachable option. `[M3]`
- **B2** As a sailor, I want to see why a spot ranked below another, so that I trust the ordering. `[M3]`
- **B3** As a visiting sailor with no history, I want a sensible ranking anyway. `[M3]`
- **B4** As a sailor, I want to filter out spots without a launch ramp for a trailered boat. `[M3]`

### Epic C — Getting there

- **C1** As a sailor, I want driving distance and time from my start point. `[M7]`
- **C2** As a sailor, I want to know where to park and how far the parking is from the launch. `[M7]`
- **C3** As a sailor, I want an Accessibility Score combining drive, parking and launch. `[M3, refined M7]`

### Epic D — On the water

- **D1** As a sailor, I want a suggested round-trip route with waypoints and an estimated duration. `[M8]`
- **D2** As a sailor, I want the forecast *along* the route, not just at the start. `[M8]`
- **D3** As a sailor, I want route estimates clearly labelled as estimates. `[M8]`

### Epic E — Afterwards

- **E1** As a sailor, I want to log an outing with conditions, route and my own rating. `[M6]`
- **E2** As a sailor, I want a map of the spots I have visited with my average rating. `[M6]`
- **E3** As a sailor, I want my history to influence future rankings. `[M9]`

### Epic F — Personalisation

- **F1** As a sailor, I want to set my preferred wind band, gust limit and temperature range. `[M9]`
- **F2** As a sailor, I want to pick a sailing profile (relax/cruising/training/racing/family/sport). `[M1]`
- **F3** As a sailor, I want the system to *propose* preference updates derived from my log, and to
  approve them rather than have them applied silently. `[M9]`

### Epic G — Safety

- **G1** As a sailor, I want explicit warnings for gusts, thunderstorms and poor visibility, visually
  separate from the score. `[M2]`
- **G2** As a sailor, I want a "return by" suggestion when conditions deteriorate later in the day. `[M2]`
- **G3** As a sailor, I want a permanent reminder to check official sources. `[M4]`

### Epic H — Assistant

- **H1** As a sailor, I want to ask in plain language and get a plan back. `[M10]`
- **H2** As a sailor, I want the assistant's numbers to be the engine's numbers, not the model's
  invention. `[M10]`

## 5. Use Cases

### UC-1 — "Where should I sail today?" (primary)

- **Actor:** sailor. **Trigger:** opens Home. **Precondition:** start location known.
- **Input:** start point, date, available hours, driving limit, sailing profile, boat class.
- **Main flow:**
  1. Resolve candidate spots within the driving limit.
  2. For each candidate, fetch (or serve from cache) the hourly forecast for the day.
  3. Compute the Sailing Score and the best window per candidate.
  4. Compute the Accessibility Score per candidate.
  5. Compute the personal affinity term from the user's log.
  6. Rank, and return the top N with component breakdowns and warnings.
- **Output:** ranked list; the top entry expands into a full Sailing Plan.
- **Alternate flows:** no candidate scores above the recommendation threshold → return the list
  anyway, headed by an explicit "no good option today" statement; provider unreachable → serve stale
  cache marked `STALE`, or fail loudly if nothing is cached. **Never** silently substitute a guess.

### UC-2 — Plan a single outing at a chosen spot

Same as UC-1 with the candidate set fixed to one spot; output is the full plan (window, route, parking,
food, warnings).

### UC-3 — Log an outing

Post-sail. The user confirms a prefilled session (date, spot, times, conditions as forecast) and adds
route, rating and notes. Actual conditions are stored separately from forecast conditions so that
forecast quality can be evaluated later.

### UC-4 — Review personal history

Visited spots, visit counts, average rating, best and worst conditions encountered, personal notes.

### UC-5 — Tune the personal profile

Explicit editing of wind band, gust limit, duration, driving limit, temperature band and default
profile. Derived suggestions are proposals requiring confirmation (F3).

### UC-6 — Ask the assistant (later)

Natural-language request → intent extraction → deterministic engine → natural-language explanation
of the engine's output. The model never computes the numbers. See [07-ai-layer.md](07-ai-layer.md).
