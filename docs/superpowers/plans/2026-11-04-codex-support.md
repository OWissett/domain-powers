# Codex Compatibility Implementation Plan

> Required workflow: use superpowers:executing-plans with test-driven development.

**Goal:** Load domain-powers in Codex and inspect its native patch edits while retaining Claude Code support.

**Architecture:** Add a Codex compatibility manifest with explicit hooks. Reuse the existing session hook with host-specific guidance and translate Codex patch payloads into the existing guard analysis.

**Contexts touched:** None; this is plugin integration tooling, with no business domain or aggregates.

**Constraints:** Python 3.11+ standard library only for scripts. Preserve Claude hook behavior, shared resource paths, and the existing nine skills. Do not claim that shell edits or skill loading have automatic hook coverage in Codex.

## Task 1: Codex plugin and patch integration

**Files:** `.codex-plugin/plugin.json`, `hooks/hooks-codex.json`, `hooks/session-start`, `scripts/domain_guard.py`, its vendored example copy, `skills/using-domain-powers/SKILL.md`, its Codex reference, installation docs, and `tests/test_codex.py`.

**Boundary:** Host-specific JSON and patch parsing stop at the hook; existing Python/Markdown analysis remains shared.

- [x] Step 1: Add subprocess tests for the documented Codex patch payload, multiple files, renamed and deleted files, unchanged legacy violations, Markdown vocabulary, session guidance, and manifest hook execution. Confirm the missing behavior fails.
- [x] Step 2: Add Codex packaging, translate patch edits into paths and changed lines, and supply filesystem-based skill/reviewer guidance. Preserve Claude behavior with regression tests.
- [x] Step 3: Document plugin and skills-only installation, trust requirements, updates, limitations, and verification commands. Keep the source layout intact.
- [x] Step 4: Run the complete tests, Ruff, strict mypy, vocabulary scan, Claude plugin validation, and example gates. Review the diff and fix actionable findings.

## Review focus

- A patch may change several files, including paths with spaces and moved files.
- Removed lines must not count as new violations; ambiguous matches must not hide violations.
- Codex reports `tool_name: apply_patch` with patch text in `tool_input.command`, even when matched by `Edit`.
- Hook configuration must preserve trust review and must not assume a Claude `Skill` tool exists.
- Skills-only installation has no lifecycle hooks; shared scripts must still resolve from their installed location.
