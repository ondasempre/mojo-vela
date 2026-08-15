# Events

Regattas, courses, club meetings near the lake you are looking at — the section that
makes SailWise feel like the sailing world rather than a weather app.

## Why this ships empty

The obvious source is a sailing news site such as veleitaliane.it. That route is not
available: a web page is not an API, and scraping one against its terms is out of scope
permanently ([data/README.md](../README.md), rule 29). There is also no open national
calendar API for Italian sailing.

So there are two routes, both legitimate:

1. **Curated entries** in `events.json` — added by you or by a club, each with a source.
2. **ICS calendar feeds** — many clubs and federations publish one. Subscribing to a
   calendar a club publishes *in order to be subscribed to* is exactly what it is for.

An empty list is an honest answer: "we have no verified events", which is different
from "there are none". The UI says it in those words.

## Adding an event

```json
{
  "id": "trofeo-esempio-2026",
  "title": "Trofeo di esempio",
  "start": "2026-09-12",
  "end": "2026-09-13",
  "category": "regatta",
  "water_body": "lago_di_como",
  "location": "Dervio",
  "organiser": "Circolo Vela Esempio",
  "url": "https://example.org/bando",
  "description": "Regata d'altura, classi ORC e Libera",
  "source_url": "https://example.org/calendario",
  "checked_at": "2026-08-15"
}
```

`category` is one of `regatta` 🏁, `course` 🎓, `social` 🎉, `event` 📅. Past events are
filtered out automatically, so old entries can stay in the file as a record.

## Subscribing a club calendar

```json
"ics_feeds": [
  {
    "name": "Circolo Vela Esempio",
    "url": "https://example.org/calendario.ics",
    "water_body": "lago_di_como"
  }
]
```

The parser handles `VEVENT` blocks with `SUMMARY`, `DTSTART`, `DTEND`, `LOCATION`,
`DESCRIPTION` and `URL`, including RFC 5545 line folding.

**It does not expand recurrence rules.** A weekly club series published as a single
recurring `VEVENT` shows only its first date. That is a deliberate limit: a parser that
half-implements `RRULE` puts wrong dates in front of someone planning a drive, which is
worse than showing one right one. If you need recurring series, expand them into
individual entries in `events.json`.

## Where events are shown

In the lake's Events section, filtered by `water_body` and sorted by date. Each entry
links to its source, so a sailor can check the notice of race rather than trusting a
summary.
