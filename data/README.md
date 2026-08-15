# `data/` — provenance rules

This directory holds the project's datasets. It has its own rules because data
carries obligations that code does not.

## Licence

**Code in this repository is MIT. The contents of `data/` are not automatically MIT.**

- Anything derived from **OpenStreetMap** is **ODbL**: attribution to
  "© OpenStreetMap contributors" is required, and a derived database must be shared
  under the same licence.
- Anything derived from **Open-Meteo** is **CC BY 4.0**: attribution required.
- Fixtures under `fixtures/` are synthetic and authored here; they are MIT like the code.

Each dataset directory carries a `SOURCES.md` naming, per file: the source, the
retrieval date, the licence, and the query or method used.

## The rule that matters

> **No coordinate, price, opening hour, phone number, rating or facility claim enters
> this directory unless it came from a named source with a retrieval date.**

Not "probably right". Not "from memory". Not "an LLM said so". A wrong coordinate for
a launch ramp is not a cosmetic bug — someone drives 80 km to a place where they
cannot put a boat in the water.

Where a fact is unavailable, the correct value is `null`, which the application
renders as `Unknown` (FR-P-03). A missing value is a fine answer; an invented one is
a defect.

## Why `spots/` is currently a schema and not a dataset

`spots/lago_di_como.seed.json` lists the spot **identities** that the Lake Como
dataset will contain, with every coordinate and facility field `null` and marked
`"status": "pending_ingestion"`.

The design session that created this repository had no network access to
OpenStreetMap, so the honest options were an empty dataset or an invented one. The
seed file is the empty one, plus the ingestion script that fills it.

To populate it:

```bash
python3 scripts/fetch_spots.py --input data/spots/lago_di_como.seed.json \
                               --output data/spots/lago_di_como.json
```

The script queries Nominatim and Overpass, respects the 1 req/s public usage policy,
sends an identifying User-Agent, and writes `source`, `source_ref` and `retrieved_at`
for every field it fills. It refuses to write a record it could not source.

For anything beyond a handful of spots, use a **Geofabrik extract** instead of the
live APIs — that is what the OSM usage policy asks bulk consumers to do, and
`scripts/fetch_spots.py --help` says so too.

## Human verification

Automated ingestion gets you a candidate. A spot is only marked
`"verified_by": "<name>", "verified_at": "<date>"` after a human has confirmed that
the launch point is real, public and usable for the stated boat size. Ranking may use
unverified spots, but the UI labels them.

## Directory map

| Path | Contents | Provenance |
|---|---|---|
| `fixtures/` | synthetic forecasts and golden outputs | authored here, SYNTHETIC |
| `spots/` | sailing spot datasets | OSM + human verification, ODbL |
| `schemas/` | JSON Schema for every dataset shape | authored here |
| `contracts/` | recorded provider payloads for contract tests | per provider's terms |
