---
name: quality-gates
description: Use when about to claim work is complete or passing, before commits or PRs, when setting up a new project or one without strict typing, linting, boundary contracts or property tests, or when CI lacks type checking, architecture checks or property tests
---

# Quality Gates

## Overview

`superpowers:verification-before-completion` says: no completion claims without fresh evidence. This skill says **what the evidence is** for a domain-driven codebase, and how to set the project up so that evidence exists.

**Core principle:** Every guarantee the other domain-powers skills describe must be checked by a command that exits non-zero when it is broken. If a guarantee has no command, it isn't one.

## The Iron Law

```
ALL GATES GREEN, RUN FRESH, IN THIS MESSAGE, BEFORE ANY "DONE".
A gate that was weakened to go green counts as red.
```

## The gates

Run in this order (cheap first), via the project's single entry point `scripts/check.sh` (template in `references/check.sh`). The gates are the same for every language; the commands come from the language variant. The last two columns are the command map for the shipped language packs.

| # | Gate | Proves | Python | Rust |
|---|---|---|---|---|
| 1 | Format | Consistent diffs | `ruff format --check .` | `cargo fmt --all --check` |
| 2 | Lint | No escapes the linter can see, no boolean traps | `ruff check .` | `cargo clippy --workspace --all-targets -- -D warnings` |
| 3 | Types | Illegal states unrepresentable; every variant handled | `mypy` (strict) | `cargo check --workspace --all-targets` |
| 4 | Boundaries | Layers point inward; domain is pure; contexts meet only at `api` | `lint-imports` | `cargo deny check bans` (plus the compiler's visibility rules) |
| 5 | Escape audit | No unjustified escape anywhere, not just in edited lines | guard `--scan src` | guard `--scan crates` |
| 6 | Tests | Invariants hold; ports honour contracts | `pytest -q` (Hypothesis `ci` profile) | `cargo test --workspace` (`PROPTEST_CASES=500`) |
| 7 | Language | Docs use one term per concept (when `docs/language.md` exists) | guard `--scan docs README.md` | same |
| 8 | Migration | No ratchet metric grew since the baseline (when `docs/domain/migration/baseline.json` exists) | Python extractor, `analyse`, `compare` | Rust extractor, `analyse`, `compare` |

The guard is `scripts/domain_guard.py` in the plugin (`../../scripts/domain_guard.py` from this SKILL.md). In a project, vendor the plugin's `scripts/domain_guard.py`, `scripts/languages/` and `scripts/assess/` together as `scripts/domain-powers/`, so the gates don't depend on the plugin being installed.

Report the result as evidence, per superpowers:
```
Gates: format ✓  lint ✓  types ✓  boundaries ✓  escapes ✓ (0)  tests ✓ (118 passed)  language ✓ (0)  migration ✓ (0 increased)
```

## Language variants

Read the variant for the project's language: `languages/python.md` or `languages/rust.md` in this skill's directory. It has the setup steps, the config templates (in `languages/<language>/`), what each gate's tool is configured to catch, and the brownfield exception lists.

## Setting up a project (once, first task of the plan)

1. Merge the variant's config templates into the project (lint rules, strict type checking, boundary contracts, the domain-powers config table).
2. Add the variant's dev dependencies.
3. Copy `references/check.sh` to `scripts/check.sh`, make it executable, and vendor the tools into `scripts/domain-powers/` as above. `check.sh` picks the command map from the manifest it finds (`Cargo.toml` → Rust, `pyproject.toml` → Python); set `DOMAIN_POWERS_LANGUAGE` to override.
4. Run `scripts/check.sh` on the existing code and **record the baseline** (counts per gate) in the plan.

### Brownfield code

Do not weaken the config to make an old codebase pass. Instead:
- Apply strict settings **per module**: strict for every new context and for every domain layer, relaxed for listed legacy modules only. That list may only shrink.
- Record existing boundary violations as listed exceptions, each with a comment linking to an issue. That list may only shrink, too.
- Treat any *growth* in a legacy list as a failed gate.

The variant names the lists for its tools.

## Never do this to go green

| Weakening | Why it's red |
|---|---|
| Adding an escape (`Any`, a cast, a suppression comment or attribute, `unsafe`, `unwrap`) without `domain-powers: allow <reason>` | Gate 5 fails, and correctly |
| Removing or loosening a type-checker flag, lint rule, or boundary contract | You changed the definition of "correct" instead of the code |
| Adding to a boundary exception list or a legacy override list | Boundary debt grew |
| Cutting property-test cases to one, skipping or ignoring an invariant test | The invariant stopped being checked |
| Deleting a failing property test "because it's flaky" | Property tools are deterministic given their seed or regression file. A "flaky" property is a real bug at an edge you didn't think of. |

If a gate seems genuinely wrong, stop and ask your human partner, with the exact gate output. Don't decide unilaterally.
