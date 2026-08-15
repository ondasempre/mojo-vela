# Running SailWise locally

**macOS / Linux / Git Bash / WSL:**

```bash
./scripts/run_local.sh          # → http://127.0.0.1:8000
```

**Windows PowerShell:**

```powershell
.\scripts\run_local.ps1        # → http://127.0.0.1:8000
```

Either one installs the two Python packages on first run, starts the API and serves
the web UI from the same process.

> PowerShell cannot run `.sh` files — that is what
> `Termine './scripts/run_local.sh' non riconosciuto` means. Use the `.ps1`, or run the
> `.sh` from Git Bash or WSL.

Both scripts must be run **from inside the repository**, so clone it first:

```powershell
git clone https://github.com/ondasempre/mojo-vela.git
cd mojo-vela
git checkout claude/sailwise-intelligent-planner-9t0qht
```

| bash | PowerShell | What you get |
|---|---|---|
| `./scripts/run_local.sh` | `.\scripts\run_local.ps1` | Real forecasts from Open-Meteo, falling back to demo data if unreachable |
| `--demo` | `-Demo` | Synthetic data only. Fully offline, nothing leaves your machine |
| `--live` | `-Live` | Open-Meteo only. Failures surface instead of falling back — use when testing the integration |
| `--reload` | `-Reload` | Auto-restart on code changes |
| `--port 9000` | `-Port 9000` | Different port |

### If PowerShell blocks the script

`.ps1` files are unsigned, so a default Windows policy may refuse to run them:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

or allow local scripts once, for your user only:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Without any script at all

Four commands, on any platform — this is exactly what the scripts do:

```powershell
python -m pip install -e ./python -e ./backend
cd backend
$env:SAILWISE_WEATHER_PROVIDER = "auto"     # or "fixture" for offline demo data
python -m uvicorn app.main:app --port 8000
```

Prefer a virtualenv:

```bash
python3 -m venv .venv && source .venv/bin/activate
./scripts/run_local.sh
```

## What happens on the first run

The spot dataset ships **without coordinates** — see [data/README.md](../data/README.md)
for why. On startup the server resolves them through Nominatim in the background, one
request per second, in priority order:

```
0s    Dervio, Colico, Torbole, Riva, Verbania…   (priority 1)
~15s  the rest of Lake Como and Garda            (priority 2)
~60s  all 33 spots resolved
```

The UI shows the progress and widens the list as spots arrive. Results are cached to
`data/spots/.geocode_cache.json` (git-ignored), so this happens **once ever**, not once
per restart.

To skip it entirely, either run a batch ingestion:

```bash
python3 scripts/fetch_spots.py --input data/spots/italian_lakes.seed.json \
                               --output data/spots/italian_lakes.json --max-spots 40
```

or disable geocoding with `SAILWISE_GEOCODING=0` (then only ingested spots are usable).

## Configuration

All environment variables, all optional:

| Variable | Default | Purpose |
|---|---|---|
| `SAILWISE_WEATHER_PROVIDER` | `auto` | `auto`, `open-meteo`, `fixture` |
| `SAILWISE_SPOTS_DATASET` | `italian_lakes` | which dataset in `data/spots/` to load |
| `SAILWISE_DATA_DIR` | `./data` | dataset location |
| `SAILWISE_GEOCODING` | `1` | resolve missing coordinates through Nominatim |
| `SAILWISE_FORECAST_TTL_S` | `900` | forecast cache TTL (15 min) |
| `SAILWISE_MAX_SPOTS` | `30` | cap on spots scored per request |
| `SAILWISE_HOST` / `SAILWISE_PORT` | `127.0.0.1` / `8000` | bind address |
| `SAILWISE_USER_AGENT` | SailWise + repo URL | required by the Nominatim usage policy |

No API keys are needed: the default provider's free tier requires none.

## API

Interactive docs at `http://127.0.0.1:8000/docs` once the server is up.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | provider in use, spot resolution progress, cache stats |
| `GET /api/spots` | the catalogue, with each spot's resolution state |
| `GET /api/profiles` | the six profiles with their weights and bands |
| `POST /api/recommendations` | **the primary endpoint** — ranked spots for a day |
| `GET /api/spots/{id}/plan` | full plan for one spot |
| `POST /api/cache/invalidate` | drop cached forecasts |

```bash
curl -s -X POST http://127.0.0.1:8000/api/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"profile":"CRUISING","min_duration_h":4,"water_body":"lago_di_como"}' | jq
```

Every response carries a `meta` block with the sources, their provenance, cache state
and age, and the safety disclaimer. `meta.demo_mode` is `true` whenever any figure in
the response is synthetic.

## Reading the UI

- **Sailing score 0–100** with the component breakdown underneath — that is *why* the
  number is what it is.
- **"sconosciuto"** on a component means the data was never sourced. It is excluded
  from the score and lowers the confidence figure; it is never counted as zero.
- **Warnings** come from a pipeline independent of the score. A red CRITICAL warning is
  never outvoted by a high number.
- **Cache age** is in the footer: `da cache (37s fa)` means the forecast was not re-fetched.
- **The demo banner** means every number on screen is invented.

## Tests

```bash
cd python  && python3 -m pytest      # 115 tests: engine, scoring, window, safety, ranking
cd backend && python3 -m pytest      #  26 tests: API, adapters, cache, provenance
./scripts/verify_env.sh              # everything, including the Mojo core if installed
```

No test touches a live service.

## Troubleshooting

**`Termine './scripts/run_local.sh' non riconosciuto`** (PowerShell) — two possible
causes, often both at once. PowerShell cannot execute `.sh` files: use
`.\scripts\run_local.ps1`. And the command must be run from inside the cloned
repository: `cd mojo-vela` first. `Get-Location` tells you where you are.

**`run_local.ps1 cannot be loaded because running scripts is disabled`** — see
"If PowerShell blocks the script" above.

**`Python non è stato trovato` / `Python was not found`, with an offer to open the
Microsoft Store** — this message does **not** come from Python. Windows ships a stub at
`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` that exists only to send you to the
Store, and it answers to `python` even when no Python is installed. Install the real
thing, then open a **new** terminal:

```powershell
winget install Python.Python.3.12
```

or download it from <https://www.python.org/downloads/windows/> with "Add python.exe to
PATH" ticked. If `python` still opens the Store afterwards, turn the stubs off in
*Settings → Apps → Advanced app settings → App execution aliases* (both `python.exe`
and `python3.exe`).

Verify before continuing — this must print a version, not an advertisement:

```powershell
python --version
```

**`Access is denied` from pip** — install into a virtual environment instead:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\scripts\run_local.ps1
```

**"Nessuno spot ha ancora coordinate"** — geocoding is disabled or Nominatim is
unreachable. Run the ingestion script, or set `SAILWISE_GEOCODING=1`.

**Demo banner when you wanted real data** — Open-Meteo was unreachable and `auto` fell
back to fixtures. Use `--live` to see the actual error instead.

**Port already in use** — `./scripts/run_local.sh --port 8080`.

**The lake dropdown is empty** — the dataset failed to load; check `SAILWISE_DATA_DIR`
points at a directory containing `spots/<dataset>.seed.json`.
