---
name: quality-gates
description: Use when about to claim Python work is complete or passing, before commits or PRs, when setting up a new Python project or one without strict typing/linting/import contracts, or when CI lacks type checking, architecture checks or property tests
---

# Quality Gates

## Overview

`superpowers:verification-before-completion` says: no completion claims without fresh evidence. This skill says **what the evidence is** for a domain-driven Python codebase, and how to set the project up so that evidence exists.

**Core principle:** Every guarantee the other domain-powers skills describe must be checked by a command that exits non-zero when it is broken. If a guarantee has no command, it isn't one.

## The Iron Law

```
ALL GATES GREEN, RUN FRESH, IN THIS MESSAGE, BEFORE ANY "DONE".
A gate that was weakened to go green counts as red.
```

## The gates

Run in this order (cheap first), via the project's single entry point `scripts/check.sh` (template in `references/check.sh`):

| # | Gate | Command | Proves |
|---|---|---|---|
| 1 | Format | `ruff format --check .` | Consistent diffs |
| 2 | Lint | `ruff check .` | No `Any` (ANN401), no blanket ignores (PGH003), no boolean traps, typed defs |
| 3 | Types | `mypy` (strict, config in pyproject) | Illegal states unrepresentable; every variant handled |
| 4 | Boundaries | `lint-imports` | Layers point inward; domain is pure; contexts meet only at `api` |
| 5 | Escape audit | `python3 <plugin>/scripts/domain_guard.py --scan src` | No unjustified `Any`/`cast`/ignore anywhere, not just in edited lines |
| 6 | Tests | `pytest -q` with `HYPOTHESIS_PROFILE=ci` | Invariants hold; ports honour contracts |
| 7 | Language | `python3 <plugin>/scripts/domain_guard.py --scan docs README.md` (when `docs/language.md` exists) | Docs use one term per concept |
| 8 | Migration | extractor, then `core.py analyse`, then `core.py compare` (when `docs/domain/migration/baseline.json` exists) | No ratchet metric grew since the baseline |

For gates 5 and 7, use this skill's base directory: the guard is at `../../scripts/domain_guard.py` relative to this SKILL.md. In CI, vendor a copy into the repo's `scripts/` so the gate doesn't depend on the plugin being installed.

Report the result as evidence, per superpowers:
```
Gates: format ✓  lint ✓  types ✓ (mypy: 0 errors in 42 files)  boundaries ✓ (6 contracts kept)  escapes ✓ (0)  tests ✓ (118 passed)  language ✓ (0)  migration ✓ (0 increased)
```

## Setting up a project (once, first task of the plan)

1. Merge `references/pyproject-template.toml` into `pyproject.toml`: ruff rules, mypy strict, import-linter contracts (adapted from `domain-powers:designing-boundaries`), `[tool.domain-powers]`.
2. Add dev dependencies: `ruff mypy import-linter hypothesis pytest`.
3. Copy `references/check.sh` to `scripts/check.sh`, make it executable, and vendor `domain_guard.py` beside it. Also vendor `skills/assessing-domain-migration/tools/` as `scripts/assess/`.
4. Run `scripts/check.sh` on the existing code and **record the baseline** (counts per gate) in the plan.

### Brownfield code

Do not weaken the config to make an old codebase pass. Instead:
- Apply strict settings **per module** via mypy `[[tool.mypy.overrides]]`: strict for every new context and for `*.domain`, relaxed for listed legacy modules only. That list may only shrink.
- Use import-linter `ignore_imports` for existing violations, each with a comment linking to an issue. That list may only shrink, too.
- Treat any *growth* in a legacy list as a failed gate.

## Never do this to go green

| Weakening | Why it's red |
|---|---|
| Adding `# type: ignore`, `Any`, `cast` without `# domain-powers: allow <reason>` | Gate 5 fails, and correctly |
| Removing or loosening a mypy flag, ruff rule, or import contract | You changed the definition of "correct" instead of the code |
| Adding to `ignore_imports` or a legacy override list | Boundary debt grew |
| `@settings(max_examples=1)`, `pytest.skip`, `xfail` on an invariant test | The invariant stopped being checked |
| Deleting a failing property test "because it's flaky" | Hypothesis is deterministic given its database. A "flaky" property is a real bug at an edge you didn't think of. |

If a gate seems genuinely wrong, stop and ask your human partner, with the exact gate output. Don't decide unilaterally.
