# Webcams

A webcam beats every forecast: it shows you the water *now*. This directory holds the
links, and it ships empty on purpose.

## Why empty

There is no free, open webcam API covering Italian lakes. The two honest routes are:

1. **This file** — cameras a human checked, with an owner and a working URL.
2. **The Windy Webcams API** — real coverage, but it needs an API key and acceptance
   of Windy's terms. Set `WINDY_WEBCAMS_API_KEY` to enable it.

The route SailWise will not take is guessing. A plausible-looking URL to a camera that
does not exist is worse than an empty section.

## Adding a webcam

Open `webcams.json` and add an entry. Only `id`, `title` and `url` are required:

```json
{
  "id": "example-marina",
  "title": "Marina — vista sul lago",
  "url": "https://example.org/webcam",
  "image_url": null,
  "embed_url": null,
  "lat": null,
  "lon": null,
  "water_body": "lago_di_como",
  "owner": "Nome del gestore",
  "verified_at": "2026-08-15",
  "note": "Aggiornata ogni 10 minuti"
}
```

| Field | Purpose |
|---|---|
| `url` | **Required.** The page a sailor opens. An entry without it is skipped. |
| `lat` / `lon` | Lets SailWise show the camera on nearby spots by distance. Without them, `water_body` is used instead. |
| `image_url` | A still image SailWise may display inline. **Only fill this in if the operator allows hotlinking.** When in doubt leave it null: the link still works. |
| `embed_url` | An embeddable player, if the operator publishes one for that purpose. |
| `owner` | Who runs the camera. Shown as credit. |
| `verified_at` | The date you last saw it working. Old dates are shown as-is, not hidden. |

## Before you add one

- Check the operator's terms for hotlinking and embedding. Linking to a public page is
  normally fine; pulling their image into your own page may not be.
- Prefer cameras that show the **water**, not the car park. The point is reading the
  surface: whitecaps, wind lanes, whether the boats are heeling at their moorings.
- A camera that shows the whole basin beats one pointing at a jetty.

## Windy Webcams

```bash
export WINDY_WEBCAMS_API_KEY=...   # then restart
```

The adapter requests cameras near each spot and links to the Windy detail page. Windy's
image URLs are token-protected and expire, which is why SailWise links rather than
embeds them.
