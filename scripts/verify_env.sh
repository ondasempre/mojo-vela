#!/usr/bin/env bash
# Milestone 1: verify the development environment end to end.
#
#   ./scripts/verify_env.sh
#
# Checks, in order:
#   1. Python reference implementation: tests + demo
#   2. Golden files are in sync with the reference
#   3. Mojo toolchain present
#   4. Mojo tests
#   5. Mojo demo
#
# Steps 3-5 are skipped with a clear message if Mojo is not installed, so that the
# Python half of the project stays usable while you are still setting up the
# toolchain (and so CI can run the Python job without Mojo).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAILURES=0

step()  { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$OFF"; }
ok()    { printf '%s  ok%s   %s\n' "$GREEN" "$OFF" "$1"; }
warn()  { printf '%s  skip%s %s\n' "$YELLOW" "$OFF" "$1"; }
fail()  { printf '%s  FAIL%s %s\n' "$RED" "$OFF" "$1"; FAILURES=$((FAILURES + 1)); }

# --- 1. Python -------------------------------------------------------------

step "Python reference implementation"
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found — install Python 3.11 or newer"
else
  ok "python3 $(python3 --version 2>&1 | cut -d' ' -f2)"

  if python3 -m pytest --version >/dev/null 2>&1; then
    if (cd python && python3 -m pytest -q); then
      ok "pytest suite"
    else
      fail "pytest suite"
    fi
  else
    warn "pytest not installed — run: pip install -e 'python[dev]'"
  fi

  if (cd python && PYTHONPATH=src python3 -m sailwise_ref.cli --profile CRUISING >/dev/null); then
    ok "reference demo runs"
  else
    fail "reference demo"
  fi
fi

# --- 2. Golden files -------------------------------------------------------

step "Golden files (Python <-> Mojo contract)"
if python3 scripts/gen_golden.py --check >/dev/null 2>&1; then
  ok "golden files are up to date"
else
  fail "golden files are stale — run: python3 scripts/gen_golden.py"
fi

if python3 scripts/check_fixture_sync.py >/dev/null 2>&1; then
  ok "Mojo fixture matches the JSON fixture"
else
  fail "fixture drift — mojo/src/sailwise/fixture.mojo disagrees with data/fixtures/"
fi

# --- 3. Mojo ---------------------------------------------------------------

step "Mojo toolchain"
if ! command -v mojo >/dev/null 2>&1 && ! command -v pixi >/dev/null 2>&1; then
  warn "neither mojo nor pixi found"
  cat <<'EOF'

  To install (see docs/milestone-1.md):

      curl -fsSL https://pixi.sh/install.sh | sh
      cd mojo && pixi install && pixi run test

  The Python half of this project works without Mojo, so nothing above is blocked.
EOF
else
  if command -v pixi >/dev/null 2>&1; then
    ok "pixi $(pixi --version 2>&1 | awk '{print $2}')"
    step "Mojo tests (via pixi)"
    if (cd mojo && pixi run test); then ok "mojo tests"; else fail "mojo tests"; fi
    step "Mojo demo"
    if (cd mojo && pixi run demo); then ok "mojo demo"; else fail "mojo demo"; fi
  else
    ok "mojo $(mojo --version 2>&1 | head -1)"
    step "Mojo tests"
    cd mojo
    for t in tests/test_units.mojo tests/test_wind.mojo; do
      if mojo run -I src "$t"; then ok "$t"; else fail "$t"; fi
    done
    if mojo run -I src -I tests tests/test_score.mojo; then
      ok "tests/test_score.mojo"
    else
      fail "tests/test_score.mojo"
    fi
    step "Mojo demo"
    if mojo run -I src main.mojo; then ok "demo"; else fail "demo"; fi
    cd "$ROOT"
  fi
fi

# --- summary ---------------------------------------------------------------

printf '\n%s' "$BOLD"
if [ "$FAILURES" -eq 0 ]; then
  printf '%sEnvironment OK.%s\n' "$GREEN" "$OFF"
  exit 0
fi
printf '%s%d check(s) failed.%s\n' "$RED" "$FAILURES" "$OFF"
exit 1
