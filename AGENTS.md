# Agent instructions

These instructions apply to agents working on domain-powers itself.

- Follow the superpowers workflow and load paired domain-powers skills. Codex
  loads skills from their files; its host-specific instructions describe native
  hooks and domain review (`skills/using-domain-powers/references/codex.md`).
- Keep script dependencies in Python 3.11+ standard library. Preserve both Claude
  Code file payloads and Codex patch payloads when changing the guard.
- Keep each example's vendored `scripts/domain-powers/` identical to the plugin's `scripts/domain_guard.py`, `scripts/languages/` and `scripts/assess/`.
- Use the documentation terms defined in `docs/language.md`.
- Run all tests, Ruff format/lint, strict mypy, plugin validation, and example gates
  before handoff. The existing contributor brief gives the exact commands and
  packaging rules (`CLAUDE.md`).
