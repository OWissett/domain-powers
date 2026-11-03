# domain-powers: agent brief

A Claude Code plugin that extends [superpowers](https://github.com/obra/superpowers) with domain-driven design, strong boundaries and type-level guarantees. Read `README.md` for what it does. This file is for agents working **on** the plugin.

## Working rules

- Follow superpowers' workflow: brainstorming → spec → writing-plans → execution → review → verification. Specs live in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
- Use the plugin's own vocabulary (`skills/defining-documentation-language/references/language-seed.md`): phase, plan, task, step, batch, round, fix wave, gate, slice. Never `stage` for a phase.
- Skill descriptions start with "Use when…" and never summarise the workflow (superpowers:writing-skills).
- Scripts are Python 3.11+ standard library only, and must pass `ruff check` (rules from `skills/quality-gates/references/pyproject-template.toml`) and `mypy --strict`.
- The plugin's `docs/` and `examples/` are not shipped in the `.plugin` archive.

## Verify

```bash
claude plugin validate .
mypy --strict scripts/*.py
# Vocabulary check of the plugin's own Markdown (copy the seed into a temporary docs/language.md):
tmp=$(mktemp -d); mkdir -p "$tmp/docs"; cp skills/defining-documentation-language/references/language-seed.md "$tmp/docs/language.md"
cp -r skills agents README.md "$tmp/"; python3 scripts/domain_guard.py --scan "$tmp"
# Example project: every gate green
cd examples/sample-shop && pip install -e . ruff mypy import-linter hypothesis pytest && ./scripts/check.sh
```

`examples/sample-shop/scripts/domain_guard.py` is a vendored copy of `scripts/domain_guard.py`. Refresh it whenever the guard changes.

## Packaging

```bash
zip -qr /tmp/domain-powers.plugin . -x ".git/*" "docs/*" "examples/*" "*.DS_Store" ".gitignore" "CLAUDE.md"
```

## Current state (2026-11-03)

- `main`: v0.2.0. Eight skills, the `domain-reviewer` agent, a SessionStart routing hook, the edit guard (Python and Markdown), and the superpowers pairing hook.
- `feature/migration-assessment`: the approved spec `docs/superpowers/specs/2026-11-03-migration-assessment-design.md`. **Next: invoke superpowers:writing-plans on it**, then have the human partner review the plan and choose subagent-driven or native execution.

## Queued work (in order)

1. **Migration assessment skill**: implement the spec above (v0.3.0).
2. **Language-pack restructure**: apply the convention from spec section 3 to everything else. Skills become agnostic with `languages/python.md` variants, the guard becomes a core plus per-language checkers, gates are defined once with a command map per language, and the reviewer checklist is split the same way. The assessment extractor's duplicated escape detection merges with the guard here. This needs its own brainstorming and spec.
3. **Rust language pack**: extractor, guard checker, gates (`cargo fmt`, `clippy -D warnings`, `cargo deny`, `proptest`) and reference files. C may follow.
