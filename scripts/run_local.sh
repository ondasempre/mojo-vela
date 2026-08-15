#!/usr/bin/env bash
# Run SailWise locally: API + web UI on http://127.0.0.1:8000
#
#   ./scripts/run_local.sh                 # real forecasts (Open-Meteo), falls back to demo data
#   ./scripts/run_local.sh --demo          # synthetic data only, fully offline
#   ./scripts/run_local.sh --port 9000
#   ./scripts/run_local.sh --reload        # auto-restart on code changes
#
# First run installs the two Python packages in editable mode. Use a virtualenv if
# you would rather not touch your system Python:
#
#   python3 -m venv .venv && source .venv/bin/activate && ./scripts/run_local.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${SAILWISE_PORT:-8000}"
HOST="${SAILWISE_HOST:-127.0.0.1}"
PROVIDER="${SAILWISE_WEATHER_PROVIDER:-auto}"
RELOAD=""

while [ $# -gt 0 ]; do
  case "$1" in
    --demo)    PROVIDER="fixture"; shift ;;
    --live)    PROVIDER="open-meteo"; shift ;;
    --port)    PORT="$2"; shift 2 ;;
    --reload)  RELOAD="--reload"; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if ! python3 -c "import fastapi" >/dev/null 2>&1; then
  echo "==> Installing dependencies (first run only)"
  python3 -m pip install -e ./python -e './backend[dev]'
fi

if ! python3 -c "import sailwise_ref" >/dev/null 2>&1; then
  python3 -m pip install -e ./python
fi

cat <<EOF

  ⛵  SailWise
      http://${HOST}:${PORT}

      weather provider : ${PROVIDER}
      spot dataset     : ${SAILWISE_SPOTS_DATASET:-italian_lakes}
      geocoding        : ${SAILWISE_GEOCODING:-on (1 req/s, cached to disk)}

  On the first run the spot coordinates are resolved in the background through
  Nominatim, one per second, in priority order — Dervio and Colico are available
  within a few seconds, the rest fill in over the next minute. The result is cached
  to disk, so this happens once ever.

  SailWise is decision support, not a safety clearance. Always check official
  forecasts and notices before departure.

EOF

cd backend
SAILWISE_WEATHER_PROVIDER="$PROVIDER" \
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" $RELOAD
