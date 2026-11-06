# Pack card: Python

**Detected by:** `pyproject.toml`, `setup.py`, `setup.cfg`, or `*.py` files. Target projects use Python ≥ 3.12.

## Config

```toml
# pyproject.toml
[tool.domain-powers]
root_package = "shop"          # top-level import name
source_root = "src"            # directory containing the root package
contexts = ["ordering", "billing"]
shared = ["shared_kernel"]     # importable from anywhere
public_module = "api"          # the only module other contexts may import
domain_forbidden = []          # extra modules banned from domain layers
```

Layout per context: `<root>/<context>/{api.py, domain/, application/, infrastructure/}`. Without the table the guard still checks type escapes and treats any `*/domain/*.py` as a domain layer.

## Guard codes

| Code | Catches |
|---|---|
| `ANY` | `typing.Any` |
| `CAST` | `typing.cast()` |
| `IGNORE` | `# type: ignore`, `# pyright: ignore`, `# mypy: ignore-errors` |
| `UNTYPED` | functions missing annotations |
| `DOMAIN-DEP` | domain importing frameworks/IO libs (`sqlalchemy`, `django`, `fastapi`, `pydantic`, `requests`, `os`, `pathlib`…) or non-domain modules |
| `LAYER` | application importing its own infrastructure |
| `CROSS-CTX` | importing another context's internals instead of its `api` |

In tests only `IGNORE` is reported. Justification: `# domain-powers: allow <reason>` on the same line, never in a domain layer.

## Variants to read

| Skill | Variant |
|---|---|
| type-driven-design | `languages/python.md`: NewType, frozen dataclasses, unions + `assert_never`, result unions |
| modeling-aggregates | `languages/python.md`: root with private state, events, unit of work, policies |
| testing-invariants | `languages/python.md`: Hypothesis strategies, `RuleBasedStateMachine`, contract suites |
| designing-boundaries | `languages/python.md`: package tree, import-linter contracts, Protocol ports |
| quality-gates | `languages/python.md`: ruff, mypy, import-linter, pytest; `languages/python/pyproject-template.toml` |
| assessing-domain-migration | extractor `scripts/assess/extractors/python.py src` |

## Reviewer checklist (Python)

Run, in addition to the agnostic checks:
- `lint-imports` (if configured) and `mypy <changed files>` (if configured).

Look for:
- `if/elif` over unions or enums without `assert_never` exhaustiveness.
- `dict[str, Any]` or `TypedDict` crossing into `domain`; pydantic models in `domain` or `application`.
- Public mutable attributes on aggregates, `__init__` callable by anyone, `update(**kw)`.
- `datetime.now()`, `uuid4()`, `os.environ`, file or network I/O inside `domain`.
- `unittest.mock` used for ports in application tests (fakes expected).
- Hypothesis settings lowered, `pytest.skip` or `xfail` on invariant tests.
- Changes to mypy, ruff or import-linter config, `[[tool.mypy.overrides]]` or `ignore_imports`.
