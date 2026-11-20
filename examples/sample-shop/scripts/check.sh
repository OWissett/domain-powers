#!/usr/bin/env bash
# Project quality gate. Copy to scripts/check.sh and vendor the domain-powers tools
# (domain_guard.py, languages/, assess/) as scripts/domain-powers/.
# The gate order is defined once; the commands come from the language's command map.
# Exits non-zero on the first failing gate; prints a one-line summary on success.
set -euo pipefail
cd "$(dirname "$0")/.."

TOOLS="${TOOLS:-scripts/domain-powers}"
GUARD="${GUARD:-$TOOLS/domain_guard.py}"
ASSESS="${ASSESS:-$TOOLS/assess}"

language="${DOMAIN_POWERS_LANGUAGE:-}"
if [ -z "$language" ]; then
  if [ -f Cargo.toml ]; then language=rust
  elif [ -f pyproject.toml ]; then language=python
  else echo "check.sh: no Cargo.toml or pyproject.toml; set DOMAIN_POWERS_LANGUAGE" >&2; exit 2
  fi
fi

# ---- command map: one function per gate, per language ----
case "$language" in
  python)
    SRC="${SRC:-src}"
    EXTRACT_ROOT="${EXTRACT_ROOT:-$SRC}"
    format()     { ruff format --check .; }
    lint()       { ruff check .; }
    types()      { mypy; }
    boundaries() { lint-imports; }
    tests()      { HYPOTHESIS_PROFILE="${HYPOTHESIS_PROFILE:-ci}" pytest -q; }
    ;;
  rust)
    SRC="${SRC:-crates}"
    EXTRACT_ROOT="${EXTRACT_ROOT:-.}"
    format()     { cargo fmt --all --check; }
    lint()       { cargo clippy --workspace --all-targets --quiet -- -D warnings; }
    types()      { cargo check --workspace --all-targets --quiet; }
    boundaries() { cargo deny --log-level error check bans; }
    tests()      { PROPTEST_CASES="${PROPTEST_CASES:-500}" cargo test --workspace --quiet; }
    ;;
  *)
    echo "check.sh: unknown language '$language'" >&2; exit 2 ;;
esac
escapes()  { python3 "$GUARD" --scan "$SRC"; }
language_docs() { python3 "$GUARD" --scan docs $( [ -f README.md ] && echo README.md ); }

MIGRATION="docs/domain/migration"
migration() {
  local out line status target=() extra=()
  out="$(mktemp -d)"
  [ -f "$MIGRATION/target.toml" ] && target=(--target "$MIGRATION/target.toml")
  if [ -f "$MIGRATION/extractor-args" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      [ -n "$line" ] && extra+=("$line")
    done < "$MIGRATION/extractor-args"
  fi
  status=0
  python3 "$ASSESS/extractors/$language.py" "$EXTRACT_ROOT" ${extra[@]+"${extra[@]}"} --out "$out/model.json" \
    && python3 "$ASSESS/core.py" analyse "$out/model.json" --out-dir "$out" ${target[@]+"${target[@]}"} \
    && python3 "$ASSESS/core.py" compare --baseline "$MIGRATION/baseline.json" --current "$out/assessment.json" \
    || status=$?
  rm -rf "$out"
  return "$status"
}

# ---- gates, in order ----
summary=()
gate() {
  local name="$1"; shift
  echo "── $name ($language)"
  if "$@"; then
    summary+=("$name ✓")
  else
    echo "✗ GATE FAILED: $name"
    exit 1
  fi
}

gate format     format
gate lint       lint
gate types      types
gate boundaries boundaries
gate escapes    escapes
gate tests      tests
if [ -f docs/language.md ]; then
  gate language language_docs
fi
if [ -f "$MIGRATION/baseline.json" ]; then
  gate migration migration
fi

echo
echo "Gates: ${summary[*]}"
