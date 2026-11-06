# Quality Gates: Python

## Command map

| # | Gate | Command | Configured to catch |
|---|---|---|---|
| 1 | Format | `ruff format --check .` | |
| 2 | Lint | `ruff check .` | No `Any` (ANN401), no blanket ignores (PGH003), no boolean traps (FBT), typed defs (ANN) |
| 3 | Types | `mypy` | `strict`, `warn_unreachable`, `disallow_any_explicit`, error codes required on ignores |
| 4 | Boundaries | `lint-imports` | Layers point inward; domain is pure; contexts meet only at `api` |
| 5 | Escape audit | `python3 scripts/domain-powers/domain_guard.py --scan src` | `ANY`, `CAST`, `IGNORE`, `UNTYPED`, boundary codes |
| 6 | Tests | `HYPOTHESIS_PROFILE=ci pytest -q` | |
| 7 | Language | `python3 scripts/domain-powers/domain_guard.py --scan docs README.md` | `TERM` |
| 8 | Migration | `extractors/python.py src`, `core.py analyse`, `core.py compare` | |

## Setup

1. Merge `languages/python/pyproject-template.toml` (in this skill's directory) into `pyproject.toml`: ruff rules, mypy strict, import-linter contracts (adapted from `domain-powers:designing-boundaries`), `[tool.domain-powers]`.
2. Add dev dependencies: `ruff mypy import-linter hypothesis pytest`.
3. Copy `references/check.sh` to `scripts/check.sh` and vendor the tools into `scripts/domain-powers/`.
4. Register the Hypothesis `ci` profile in `tests/conftest.py` (see `domain-powers:testing-invariants`, Python variant).

## Brownfield lists

- **mypy:** `[[tool.mypy.overrides]]` with `module = [...]` for listed legacy modules only, relaxing `strict` and `disallow_any_explicit`. Every new context and every `*.domain` stays strict.
- **import-linter:** `ignore_imports` per contract, each line with a comment linking to an issue.

Both lists may only shrink.

## Never do this to go green (Python spellings)

- `# type: ignore`, `Any`, `cast` without `# domain-powers: allow <reason>`
- Removing a mypy flag, a ruff rule from `select`, or an import-linter contract
- `@settings(max_examples=1)`, `pytest.skip`, `xfail` on an invariant test
