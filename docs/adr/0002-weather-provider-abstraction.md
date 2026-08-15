# ADR 0002 — Weather provider abstraction, and why Windy is not the default

- **Status:** accepted
- **Date:** 2026-08-15 (terms verified on this date; re-verify before any deployment)

## Context

The brief names Windy as the primary meteorological reference. Before building on it, the access
terms were checked, since §29 of the brief requires exactly that.

What the check found:

- The Point Forecast API is a real, documented API (`POST https://api.windy.com/api/point-forecast/v2`)
  with an API key, multiple models and a rich parameter set — technically an excellent fit.
- The **trial tier is documented as being for development purposes only.**
- The **Professional tier is a paid annual subscription**, with daily limits raised only by explicit
  agreement covering the intended use.
- Community guidance from Windy indicates that using the API to build a *weather application* falls
  outside the standard terms.
- Windy's web site is not an API, and scraping it is out of the question (brief §29).

Meanwhile Open-Meteo offers a free, key-less tier for **non-commercial** use at up to **10,000
calls/day**, with data under **CC BY 4.0** (attribution required) and paid plans for commercial use.
For an open-source, non-commercial project, that is a clean fit.

## Decision

1. **All weather access goes through a `WeatherProvider` port.** No domain type, service or API schema
   names any provider.
2. **Open-Meteo is the default adapter**, with visible CC BY 4.0 attribution in the UI and in API
   responses.
3. **The Windy adapter is optional, off by default, and key-gated.** Its enabling flag is named
   `WINDY_ENABLED_I_HAVE_CHECKED_THE_TERMS` so that the operator is confronted with the obligation.
   The trial key is used for development only.
4. **A `FixtureWeatherProvider` always exists** for tests, demos and offline work — no test in this
   repository ever touches a live provider.
5. **Adapters declare capabilities.** Fields a provider cannot supply are `UNKNOWN`, never defaulted.
6. **Windy is used for visualisation via its embeddable map/widget** under the widget's own terms —
   this satisfies the brief's actual intent (Windy as the visual and conceptual reference) without a
   data licence.
7. **The licence table in [06-integrations.md](../06-integrations.md) is re-verified each release**
   and the verification date recorded.

## Consequences

**Positive**

- The project can be published and run publicly today, licence-clean.
- Adding, swapping or removing a provider is a configuration change.
- Multiple providers open a genuinely useful feature: surfacing model disagreement (FR-W-06).

**Negative**

- The default provider's model selection is narrower than Windy's premium models.
- Two adapters mean two sets of contract tests and two normalisation paths to maintain.
- If the project ever goes commercial, the weather licensing question reopens — deliberately, and
  with the abstraction already in place to answer it cheaply.

## Notes

Terms and pricing for all providers change. This ADR records a decision *and* a verification date; it
does not certify current terms. Anyone deploying SailWise is responsible for checking the terms that
apply to them.
