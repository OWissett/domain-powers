# domain-powers: agent brief

A Claude Code and Codex plugin that extends [superpowers](https://github.com/obra/superpowers) with domain-driven design, strong boundaries and type-level guarantees. Its README describes skill routing and edit enforcement. This file is for agents working **on** the plugin.

## Working rules

- Follow superpowers' workflow: brainstorming → spec → writing-plans → execution → review → verification. Specs live in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
- Use the plugin's own vocabulary (`skills/defining-documentation-language/references/language-seed.md`): phase, plan, task, step, batch, round, fix wave, gate, slice. Never `stage` for a phase.
- Skill descriptions start with "Use when…" and never summarise the workflow (superpowers:writing-skills).
- Scripts are Python 3.11+ standard library only, and must pass `ruff format --check`, `ruff check` (config in `ruff.toml`) and `mypy --strict`.
- Language packs: agnostic files never name a language's syntax or tools. Language detail goes in `skills/<skill>/languages/<language>.md`, `scripts/languages/<language>.py` and `scripts/assess/extractors/<language>.py` (README, Language packs).
- The plugin's `docs/` and `examples/` are not shipped in the `.plugin` archive.

## Verify

```bash
claude plugin validate .
uv run --python 3.13 --with pytest pytest tests -q                            # TEST (guard, assessment, host compatibility)
uvx ruff format --check scripts tests && uvx ruff check scripts tests   # LINT
uvx --python 3.13 mypy --strict scripts/*.py scripts/languages/*.py scripts/assess/*.py scripts/assess/extractors/*.py   # TYPES
# Vocabulary check of the plugin's own Markdown (copy the seed into a temporary docs/language.md):
tmp=$(mktemp -d); mkdir -p "$tmp/docs"; cp skills/defining-documentation-language/references/language-seed.md "$tmp/docs/language.md"
cp -r skills agents README.md "$tmp/"; python3 scripts/domain_guard.py --scan "$tmp"
# Example projects: every gate green
(cd examples/sample-shop && pip install -e . ruff mypy import-linter hypothesis pytest && ./scripts/check.sh)
(cd examples/rust-shop && ./scripts/check.sh)   # needs rustfmt, clippy, cargo-deny
```

Both examples vendor `scripts/domain_guard.py`, `scripts/languages/` and `scripts/assess/` as `scripts/domain-powers/`, and copy `skills/quality-gates/references/check.sh` as `scripts/check.sh`. Refresh them whenever the tools change:

```bash
for ex in examples/sample-shop examples/rust-shop; do
  rm -rf "$ex/scripts/domain-powers" && mkdir -p "$ex/scripts/domain-powers"
  cp -r scripts/domain_guard.py scripts/languages scripts/assess "$ex/scripts/domain-powers/"
  find "$ex/scripts/domain-powers" -name __pycache__ -prune -exec rm -rf {} +
  cp skills/quality-gates/references/check.sh "$ex/scripts/check.sh"
done
```

## Packaging

```bash
zip -qr /tmp/domain-powers.plugin . -x ".git/*" "docs/*" "examples/*" "tests/*" "*.DS_Store" ".gitignore" "CLAUDE.md" "ruff.toml" ".superpowers/*" ".mypy_cache/*" ".pytest_cache/*" ".ruff_cache/*" "*/__pycache__/*" "*.pyc"
```

## Current state (2026-11-06)

- `main`: v0.3.0 with Codex support. Nine skills, the `domain-reviewer` agent, SessionStart routing hooks (Claude Code and Codex), the edit guard (Python and Markdown), the superpowers pairing hook, and the migration assessment tools.
- `feature/language-packs`: v0.4.0. The plugin is an agnostic core plus Python and Rust language packs: agnostic skills with `languages/` variants and pack cards, the guard split into a core and `scripts/languages/`, assessment tools moved to `scripts/assess/` with a Rust extractor, gates defined once in `check.sh` with a command map per language, and `examples/rust-shop`. Spec: `docs/superpowers/specs/2026-11-06-language-packs-design.md`.

## Queued work

1. **C language pack** (or another language): pack card, skill variants, guard module, extractor, `check.sh` case, example.
