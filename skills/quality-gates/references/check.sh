#!/usr/bin/env bash
# Project quality gate. Copy to scripts/check.sh and vendor domain_guard.py beside it.
# Exit non-zero on the first failing gate; print a one-line summary on success.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${SRC:-src}"
GUARD="${GUARD:-scripts/domain_guard.py}"
summary=()

gate() {
  local name="$1"; shift
  echo "── $name: $*"
  if "$@"; then
    summary+=("$name ✓")
  else
    echo "✗ GATE FAILED: $name"
    exit 1
  fi
}

gate format     ruff format --check .
gate lint       ruff check .
gate types      mypy
gate boundaries lint-imports
gate escapes    python3 "$GUARD" --scan "$SRC"
HYPOTHESIS_PROFILE="${HYPOTHESIS_PROFILE:-ci}" gate tests pytest -q
if [ -f docs/language.md ]; then
  gate language python3 "$GUARD" --scan docs $( [ -f README.md ] && echo README.md )
fi

echo
echo "Gates: ${summary[*]}"
