# Migration Assessment Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `domain-powers:assessing-domain-migration` (v0.3.0): a Python extractor and an agnostic core that measure a codebase, propose contexts, score it, measure distance to an agreed target, and ratchet every later change against a committed baseline.

**Architecture:** The extractor (`tools/extractors/python.py`) parses source with `ast` and writes a neutral `model.json`. The core (`tools/core.py`) never parses source. It reads the model and writes `assessment.json` and `assessment.md` (`analyse`), and it checks a current assessment against a baseline (`compare`). The skill's Markdown drives the seven phases; the plugin gains a `migration` gate, a reviewer migration mode and the term *slice*.

**Tech Stack:** Python 3.11+ standard library (`ast`, `tokenize`, `tomllib`, `json`, `fnmatch`, `subprocess`, `argparse`); pytest for tests only.

**Spec:** `docs/superpowers/specs/2026-11-03-migration-assessment-design.md`. Read it before every task; section numbers below refer to it.

## Global Constraints

- Tools are Python 3.11+ standard library only. Tests may use pytest; nothing else.
- Tools pass `ruff format --check`, `ruff check` (repo `ruff.toml`) and `mypy --strict`.
- No `Any`, no `cast`, no `# type: ignore` anywhere in tools or tests: the edit guard flags them. Read JSON as `object` and narrow with `isinstance` into dataclasses.
- Test fixtures that need escapes (`Any`, `cast`, `# type: ignore`, untyped defs) are written as **string literals** into `tmp_path`, never as files in the repo, so the guard does not see them.
- Schema identifiers, verbatim: `domain-powers.assess.model/1`, `domain-powers.assess.result/1`.
- Exit codes: extractor 0 success (even with skipped files), 2 usage error or unreadable root. `analyse` 0 success, 2 usage, schema or target error. `compare` 0 nothing increased, 1 something increased, 2 schema or usage error.
- Output is deterministic: no timestamps; every list sorted; JSON written with `json.dumps(obj, indent=2, sort_keys=True) + "\n"`; floats rounded to 4 decimal places when serialised.
- Anything a missing capability prevents is *not applicable* (`None` plus a reason), never zero.
- `core.py` and `SKILL.md` never name a language's syntax or tools (spec section 3). Language specifics live in the extractor and in `EXTRACTORS.md`.
- Markdown uses the plugin vocabulary (`skills/defining-documentation-language/references/language-seed.md`): phase, plan, task, step, gate, checkpoint, slice. Never `stage`, `iteration`, `increment`, `migration step`, `migration phase`, `interface`.
- Skill descriptions start with "Use when…" and never summarise the workflow.
- `docs/`, `examples/` and `tests/` are not shipped in the `.plugin` archive.

**Commands** (on the current dev machine `python3` is 3.10 and `ruff` is not on PATH, so use `uv`):

```bash
uv run --python 3.13 --with pytest pytest tests/assess -q                     # TEST
uvx ruff format --check scripts skills tests && uvx ruff check scripts skills tests   # LINT
uvx --python 3.13 mypy --strict scripts/*.py skills/assessing-domain-migration/tools/core.py skills/assessing-domain-migration/tools/extractors/python.py   # TYPES
```

`T=skills/assessing-domain-migration/tools` throughout.

## Review Focus

1. **A source root holding a virtualenv, hidden or build directories** (`.venv`, `venv`, `.tox`, `build`, `dist`, `node_modules`, `site-packages`, `*.egg-info`, any dir with `pyvenv.cfg`): the extractor skips them instead of measuring thousands of third-party modules. Test in Task 2.
2. **A file that is not UTF-8:** it is listed in `skipped` with reason `not UTF-8` and the run exits 0. Test in Task 2.
3. **A long import chain (thousands of units in one cycle):** cycle detection is iterative and raises no `RecursionError`. Test in Task 4.
4. **`analyse --churn` run from a directory where git paths don't match unit paths:** churn is *not applicable* with reason `no git paths matched units`, not a column of zeros. Test in Task 4.
5. **A target context whose patterns match no unit (a typo):** it is listed in `distance.empty_contexts` and shown in the report. Test in Task 5.

---

### Task 1: Neutral model and test harness

**Files:**
- Create: `$T/core.py` (model section only)
- Create: `tests/assess/conftest.py`, `tests/assess/helpers.py`, `tests/assess/test_model.py`
- Modify: `ruff.toml` (add `[lint.per-file-ignores]` `"tests/**" = ["S101", "S603", "S607", "PLR2004"]`)
- Modify: `CLAUDE.md` (Verify: add the TEST command and widen LINT/TYPES to the tools as in the Commands block; Packaging: add `"tests/*"` to the zip excludes)

**Interfaces:**
- Produces (in `core.py`):
  - `MODEL_SCHEMA = "domain-powers.assess.model/1"`, `RESULT_SCHEMA = "domain-powers.assess.result/1"`
  - `CAPABILITIES: frozenset[str]` = the six of spec 5.1
  - `HINTS: tuple[str, ...]` (spec 5.2, in order); `MODEL_LIKE`, `SERVICE_LIKE`, `EDGE`, `SHARED: frozenset[str]` (spec 5.2 groups)
  - `Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]`
  - `NotApplicable = dict[str, str]` (metric key → reason). Every metric key is the name of the `Assessment` field it fills (Task 8): `layout`, `unit_cycles`, `group_cycles`, `hubs`, `coupling`, `churn`, `terms`, `richness`, `framework`, `escapes`, `clusters`, `distance`, plus `scorecard.<dimension>`.
  - `class ModelError(Exception)`
  - frozen dataclasses: `TypeDecl(name: str, data_only: bool | None)`, `Unit(id: str, path: str, group: str, loc: int, layer_hint: str | None, types: tuple[TypeDecl, ...], escapes: dict[str, int], framework_refs: tuple[str, ...])`, `Edge(source: str, target: str, count: int)`, `Skipped(path: str, reason: str)`, `Model(language: str, root: str, capabilities: frozenset[str], units: tuple[Unit, ...], edges: tuple[Edge, ...], skipped: tuple[Skipped, ...])` with `Model.has(capability: str) -> bool`
  - `parse_model(raw: object) -> Model`: validates, defaults optional unit fields (`layer_hint` None, `types` (), `escapes` {}, `framework_refs` ()), sorts units by `id` and edges by `(source, target)`. JSON key `from`/`to` maps to `source`/`target`.
  - `load_model(path: Path) -> Model`: raises `ModelError` on unreadable file or bad JSON too
  - `require(model: Model, na: NotApplicable, metric: str, *capabilities: str) -> bool`: records `"missing capability: <first missing>"` under `metric` and returns False when any is missing
- Produces (in `tests/assess/helpers.py`): `unit(id: str, *, group: str | None = None, hint: str | None = None, types: Sequence[tuple[str, bool]] = (), loc: int = 10, escapes: dict[str, int] | None = None, refs: Sequence[str] = ()) -> dict[str, object]` (group defaults to `id` minus its last segment), `make_model(units: Sequence[dict[str, object]], edges: Sequence[tuple[str, str, int]] = (), *, capabilities: Sequence[str] | None = None) -> core.Model` (all six capabilities by default; builds the raw dict and calls `parse_model`), `write_tree(root: Path, files: dict[str, str]) -> None`.
- `conftest.py` puts `$T` and `tests/assess` on `sys.path`, so tests use `import core`, `from extractors import python as pyx`, `from helpers import ...`.

- [ ] **Step 1: Write the failing tests** in `tests/assess/test_model.py`

```python
def test_parse_sorts_units_and_edges() -> None:
    m = make_model([unit("b.y"), unit("a.x")], [("b.y", "a.x", 2)])
    assert [u.id for u in m.units] == ["a.x", "b.y"]
    assert m.edges == (core.Edge("b.y", "a.x", 2),)
    assert m.units[0].group == "a" and m.units[0].layer_hint is None

def test_wrong_schema_raises() -> None:      # raw dict with schema ".../2"
    with pytest.raises(core.ModelError, match="domain-powers.assess.model/1"): ...

def test_edge_to_unknown_unit_raises() -> None: ...       # ModelError, message names the id
def test_duplicate_unit_id_raises() -> None: ...          # ModelError
def test_non_object_json_raises(tmp_path: Path) -> None:  # load_model on "[]" -> ModelError

def test_require_records_first_missing_capability() -> None:
    m = make_model([unit("a.x")], capabilities=["types"])
    na: core.NotApplicable = {}
    assert not core.require(m, na, "unit_cycles", "edges")
    assert na == {"unit_cycles": "missing capability: edges"}
    assert core.require(m, na, "terms", "types")
```

- [ ] **Step 2: Run** TEST. Expected: FAIL, `ModuleNotFoundError: No module named 'core'`.
- [ ] **Step 3: Implement** the model section of `core.py` and the helpers. Module docstring states the two commands and that the core never parses source.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git add ruff.toml CLAUDE.md tests/assess $T/core.py && git commit -m "assess: neutral model and test harness"`

---

### Task 2: Python extractor, structure

**Files:**
- Create: `$T/extractors/python.py`
- Test: `tests/assess/test_python_extractor.py`

**Interfaces:**
- Consumes: nothing from `core.py`. The extractor is a separate command and must not import the core (spec 4).
- Produces:
  - `extract(source_root: Path, *, package: str | None = None, include_tests: bool = False, exclude: Sequence[str] = ()) -> dict[str, Json]` (own `Json` alias, same shape as the core's)
  - `main(argv: list[str]) -> int`, command line as spec 5.3: `python.py <source_root> --out model.json [--package NAME] [--include-tests] [--exclude GLOB ...]`
  - `CAPABILITIES_DECLARED = ("data_only", "edges", "escapes", "framework_refs", "layer_hints", "types")`
  - In this task `types`, `escapes` and `framework_refs` are emitted empty; Task 3 fills them.

Rules this task pins (spec 5.3, 5.4, 10):
- Walk `*.py` under the root in sorted order. Skip directories named `__pycache__`, `venv`, `node_modules`, `build`, `dist`, `site-packages`, names starting with `.`, names ending `.egg-info`, and any directory containing `pyvenv.cfg`.
- `id`: dotted path relative to the root, `__init__` dropped. Directories without `__init__.py` are still packages.
- `path`: `(source_root / relative).as_posix()` using the root as given, so running with `src` from the project root yields `src/shop/models/order.py`. `root` in the model is `source_root.as_posix()`.
- Root package: `--package` (exit 2 if no such directory), otherwise the single top-level directory when the root holds exactly one directory containing `.py` files and no top-level `.py` files; otherwise none.
- `group`: with a root package, its first two segments (`shop.models`), or the root package itself for modules directly in it; without one, the first segment.
- `layer_hint`: test patterns first (any segment `tests` or `test`, file `test_*.py`, `*_test.py`, `conftest.py` → `tests`). Otherwise check the id's segments below the root package from last to first; the first that maps wins. Map: each spec 5.2 hint to itself, plus `model→models`, `entity→entities`, `schema→schemas`, `service→services`, `manager→managers`, `handler→handlers`, `view→views`, `controller→controllers`, `route→routes`, `repos→repositories`, `repo→repositories`, `repository→repositories`, `serializer→serializers`, `form→forms`, `task→tasks`, `util→utils`, `helper→helpers`, `adapter→adapters`, `infra→infrastructure`. No match → `None`.
- `loc`: lines whose stripped text is non-empty and does not start with `#`.
- Edges: each `import` alias and each `from … import` alias contributes one count. Target = longest dotted prefix of the imported name that is a unit. For `from pkg import name`, try `pkg.name` first, then `pkg`. Relative imports are resolved against the unit's package (as `resolve_relative` in `scripts/domain_guard.py`). Self-edges and non-unit targets are dropped. Edges to dropped units (tests, excluded) are dropped too.
- `--exclude` globs are `fnmatch`ed against the posix path relative to the root.
- Skipped: `SyntaxError` → `syntax error`; `UnicodeDecodeError` → `not UTF-8`.

- [ ] **Step 1: Write the failing tests.** Each builds a tree with `write_tree(tmp_path / "src", {...})` and `monkeypatch.chdir(tmp_path)`.

```python
def test_ids_paths_and_groups(...)        # shop/models/order.py -> id "shop.models.order", group "shop.models",
                                          # path "src/shop/models/order.py"; shop/cli.py -> group "shop"; model["root"] == "src"
def test_no_root_package_groups_by_first_segment(...)  # src/a/x.py, src/b/y.py -> groups "a", "b"
def test_loc_skips_blank_and_comment_lines(...)        # "x = 1\n\n# c\n  # d\ny = 2\n" -> 2
@pytest.mark.parametrize("rel,hint", [("shop/models/order.py", "models"), ("shop/repos/x.py", "repositories"),
    ("shop/billing/views.py", "views"), ("shop/ordering/thing.py", None), ("shop/models/__init__.py", "models")])
def test_layer_hints(...)
def test_edges_resolution(...)
    # shop/models/__init__.py, shop/models/order.py, shop/services/a.py with:
    #   import shop.models.order          -> (shop.services.a, shop.models.order)
    #   from ..models import order        -> same pair; count now 2
    #   from shop.models import Thing     -> (shop.services.a, shop.models)
    #   import shop.models.order.missing  -> longest prefix: shop.models.order; count now 3
    #   import json                       -> no edge
    # edges == [{"from": "shop.services.a", "to": "shop.models", "count": 1},
    #           {"from": "shop.services.a", "to": "shop.models.order", "count": 3}]
def test_namespace_packages_without_init(...)          # no __init__.py anywhere; units and edges still found
def test_tests_excluded_by_default_and_included_with_flag(...)  # tests/test_x.py; with flag hint == "tests"
def test_exclude_glob(...)                             # exclude=["shop/generated/*"] drops those units and their edges
def test_syntax_error_is_skipped(...)                  # skipped == [{"path": "src/shop/bad.py", "reason": "syntax error"}]
def test_non_utf8_is_skipped(...)                      # bytes b"\xff\xfe x = 1"; reason "not UTF-8"
def test_skips_environment_and_hidden_dirs(...)        # .venv/, venv/, build/, x.egg-info/, dir with pyvenv.cfg -> no units
def test_capabilities_declared(...)                    # sorted list of all six
def test_output_is_byte_identical_across_runs(...)     # main() twice to two files, compare bytes
def test_cli_exit_codes(...)                           # missing root -> 2; --package nope -> 2; good -> 0 and schema field set
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on import of `extractors.python`.
- [ ] **Step 3: Implement** `extract` and `main` in `$T/extractors/python.py`. Units sorted by `id`, edges by `(from, to)`, skipped by `path`.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git add $T/extractors tests/assess/test_python_extractor.py && git commit -m "assess: python extractor units, hints and edges"`

---

### Task 3: Python extractor, types, escapes and framework refs

**Files:**
- Modify: `$T/extractors/python.py`
- Test: `tests/assess/test_python_extractor.py`

**Interfaces:**
- Produces: `FRAMEWORK_REFS: tuple[str, ...]`, a copy of `DEFAULT_DOMAIN_FORBIDDEN` from `scripts/domain_guard.py`, with a comment saying it is duplicated until the language-pack restructure merges the two. Escape detection copies the guard's `check_types` rules, with the same comment.

Rules this task pins (spec 5.1, 5.4):
- `types`: module-level `class` statements only, in source order.
- `data_only` is true when every statement in the class body is one of: an annotated or plain assignment, `pass`, a bare constant expression (docstring, `...`), a nested class named `Meta` or `Config`, or a function that is a dunder (`__x__`) or is decorated with `property`, `cached_property`, `functools.cached_property`, or `<name>.setter` / `.getter` / `.deleter`. Class decorators (such as `@dataclass`) do not matter.
- `escapes`: one count per guard finding. `ANY` counts once per line (the import line counts too), `CAST` per call, `IGNORE` per suppression comment, `UNTYPED` per function. A line carrying `domain-powers: allow <reason>` drops its findings, except in units whose path has a `domain` directory segment. In `tests` units only `IGNORE` counts. Kinds with zero count are omitted.
- `framework_refs`: sorted unique top segments of absolute imports that are in `FRAMEWORK_REFS`.

- [ ] **Step 1: Write the failing tests** (sources as strings)

```python
def test_data_only_rules(...)
    # @dataclass class A: x: int; y: str = ""          -> True
    # class B: with @property, __eq__, docstring         -> True
    # class C(Model): name = Column(); class Meta: ...   -> True
    # class D: def total(self) -> int: ...               -> False
    # def f() -> None: class Inner: ...                  -> not listed
    # types == [{"name": "A", "data_only": True}, ...] in source order
def test_escape_kinds(...)
    # "from typing import Any, cast\n" "def f(x: Any) -> None:\n" "    y = cast(int, x)  # type: ignore[misc]\n"
    # "def g(z):\n    return z\n"
    # escapes == {"ANY": 2, "CAST": 1, "IGNORE": 1, "UNTYPED": 1}
def test_allow_justification_outside_domain_only(...)
    # same line "x: Any = 1  # domain-powers: allow legacy" in shop/web/a.py -> ANY counts only the import line;
    # in shop/billing/domain/a.py -> both lines count
def test_tests_units_count_only_ignore(...)            # include_tests=True; test file with Any and a type-ignore -> {"IGNORE": 1}
def test_framework_refs(...)
    # "import sqlalchemy.orm\nfrom flask import Flask\nimport os\nfrom . import x\nimport shop.y\n"
    # framework_refs == ["flask", "os", "sqlalchemy"]
```

- [ ] **Step 2: Run** TEST. Expected: the five new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "assess: python extractor types, escapes and framework refs"`

---

### Task 4: Shape metrics

**Files:**
- Modify: `$T/core.py` (shape section)
- Test: `tests/assess/test_shape.py`

**Interfaces:**
- Consumes: `Model`, `NotApplicable`, `require`, hint groups (Task 1).
- Produces:
  - `strongly_connected(nodes: Sequence[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]`: iterative Tarjan; returns only components of size > 1, each sorted, the list sorted.
  - `layout_style(model: Model, na: NotApplicable) -> str | None`: one of `"feature packages"`, `"technical layering"`, `"mixed"`. Check feature packages first: at least two groups each contain a model-like, a service-like and an edge unit, and those groups hold ≥ 50% of units. Then technical layering: ≥ 50% of units have a hint other than `domain`, `application`, `infrastructure`, `adapters`, `tests` or `None`. Otherwise mixed. Needs `layer_hints`.
  - `unit_cycles(model, na) -> list[list[str]] | None` (needs `edges`)
  - `group_cycles(model, na) -> list[list[str]] | None`. Not applicable with reason `fewer than two groups` or `no internal edges` (no edges between different groups).
  - `@dataclass(frozen=True) Hub(id: str, fan_in: int)`; `hubs(model, na) -> list[Hub] | None`: fan-in = distinct units with an edge into the unit; top 10, sorted fan-in descending then id.
  - `@dataclass(frozen=True) GroupCoupling(group: str, ca: int, ce: int, instability: float | None)`; `coupling(model, na) -> list[GroupCoupling] | None`: `ca` = distinct units outside the group with an edge into it; `ce` = distinct units outside the group that its units depend on; `I = ce / (ca + ce)`, `None` when both are 0. Sorted by group. Same not-applicable rules as `group_cycles`.
  - `parse_numstat(text: str) -> dict[str, int]`: path → added + deleted, summed; skips binary (`-`) and rename (`=>`) lines.
  - `@dataclass(frozen=True) UnitChurn(id: str, lines: int)`; `churn(model: Model, cwd: Path, na: NotApplicable) -> list[UnitChurn] | None`: runs `git -C <cwd> log --numstat --format= --relative --since=12.months.ago` (`subprocess.run`, list args, `check=False`; `# noqa: S603, S607` on that line only). Reasons: `git unavailable` (`FileNotFoundError`), `not a git repository` (non-zero exit), `no git paths matched units`. Units with 0 lines are omitted; sorted lines descending, then id.

- [ ] **Step 1: Write the failing tests**

```python
def test_strongly_connected_finds_cycles() -> None:
    edges = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "e"), ("e", "c"), ("e", "f")]
    assert core.strongly_connected(list("fedcba"), edges) == [["a", "b"], ["c", "d", "e"]]
def test_strongly_connected_is_iterative() -> None:   # 5000-node chain n0->n1->...->n4999->n0: one component, len 5000
def test_layout_technical_layering() -> None: ...     # hints models, services, views, utils -> "technical layering"
def test_layout_feature_packages() -> None: ...       # groups shop.orders and shop.billing each with models/services/views units
def test_layout_mixed() -> None: ...                  # 3 of 4 units hint None -> "mixed"
def test_layout_not_applicable_without_hints() -> None: ...   # na["layout"] == "missing capability: layer_hints"
def test_unit_and_group_cycles() -> None: ...
def test_group_metrics_need_two_groups() -> None:     # na["group_cycles"] == na["coupling"] == "fewer than two groups"
def test_group_metrics_need_internal_edges() -> None: # reason "no internal edges"
def test_hubs_top_ten_ties_by_id() -> None: ...       # 12 importees; 11th with equal fan-in cut by id
def test_instability() -> None:                       # a.x -> b.y; group c isolated
    assert core.coupling(m, {}) == [core.GroupCoupling("a", 0, 1, 1.0), core.GroupCoupling("b", 1, 0, 0.0),
                                    core.GroupCoupling("c", 0, 0, None)]
def test_parse_numstat() -> None:
    text = "3\t2\tsrc/a.py\n-\t-\tlogo.png\n\n1\t0\tsrc/{old => new}.py\n4\t0\tsrc/a.py\n"
    assert core.parse_numstat(text) == {"src/a.py": 9}
def test_churn_outside_git(tmp_path: Path) -> None: ...      # None, na["churn"] == "not a git repository"
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_churn_counts_lines(tmp_path: Path) -> None: ...     # git init, commit src/a.py twice -> [UnitChurn("a", n)]
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_churn_no_matching_paths(tmp_path: Path) -> None: ...  # repo exists, unit paths differ -> "no git paths matched units"
```

- [ ] **Step 2: Run** TEST. Expected: FAIL, `AttributeError` on `core.strongly_connected`.
- [ ] **Step 3: Implement** the shape section.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "assess: shape metrics (layout, cycles, hubs, churn)"` (add the new test file first)

---

### Task 5: Target and distance

**Files:**
- Modify: `$T/core.py` (target section)
- Test: `tests/assess/test_target.py`

**Interfaces:**
- Consumes: `Model`, `strongly_connected` (Task 4).
- Produces:
  - `class TargetError(Exception)`; `class OverlapError(TargetError)` with attribute `overlaps: dict[str, list[str]]` (unit → sorted contexts); its message lists each unit and its contexts.
  - `@dataclass(frozen=True) Context(name: str, classification: str, units: tuple[str, ...], public: tuple[str, ...])`; `@dataclass(frozen=True) Target(contexts: tuple[Context, ...])`, contexts sorted by name.
  - `parse_target(text: str) -> Target` (`tomllib`; `classification` must be `core`, `supporting` or `generic`; `units` a non-empty list of strings; `public` optional, default empty). Errors are `TargetError` naming the context and field. `load_target(path: Path) -> Target`.
  - `target_json(target: Target) -> dict[str, Json]`: `{"contexts": {name: {"classification", "units", "public"}}}`, the form stored in `assessment.json` and compared by `compare`.
  - `assign_units(model: Model, target: Target) -> dict[str, str]`: unit id → context for matched units (`fnmatch.fnmatchcase` on id); raises `OverlapError`.
  - `is_public(unit_id: str, context: Context) -> bool`
  - dataclasses `ContextPair(source: str, target: str, via_public: int, into_internals: int)`, `WorkItem(source: str, target: str, source_context: str, target_context: str, count: int)`, `Distance(unassigned: list[str], pairs: list[ContextPair], context_cycles: list[list[str]], work_list: list[WorkItem], empty_contexts: list[str])`
  - `distance(model: Model, target: Target, na: NotApplicable) -> Distance | None`: needs `edges`. Counts are sums of edge `count`. Edges with an unassigned end are ignored. Pairs sorted by `(source, target)`; work list sorted by `(source_context, target_context)`, then count descending, then `(source, target)`.

- [ ] **Step 1: Write the failing tests**

```python
SPEC_TARGET = '''  (the toml example from spec 6.5, verbatim)  '''
def test_parse_target() -> None:
    t = core.parse_target(SPEC_TARGET)
    assert [c.name for c in t.contexts] == ["billing", "ordering"]
    assert t.contexts[1] == core.Context("ordering", "core", ("shop.models.order*", "shop.services.checkout*"),
                                         ("shop.services.checkout",))
def test_bad_classification() -> None: ...       # "kernel" -> TargetError matching "classification"
def test_missing_units() -> None: ...            # TargetError matching "units"
def test_overlap_lists_units_and_contexts() -> None:
    with pytest.raises(core.OverlapError) as e: core.assign_units(m, t)   # "shop.x" matched by a and b
    assert e.value.overlaps == {"shop.x": ["a", "b"]} and "shop.x" in str(e.value)
def test_distance() -> None:
    # ordering = o.*, public o.api; billing = b.*, public b.api; unassigned u.z
    # edges: o.core->b.api 1, o.core->b.core 3, b.core->o.core 1, u.z->o.core 5
    d = core.distance(m, t, {})
    assert d.unassigned == ["u.z"]
    assert d.pairs == [core.ContextPair("billing", "ordering", 0, 1), core.ContextPair("ordering", "billing", 1, 3)]
    assert d.context_cycles == [["billing", "ordering"]]
    assert [(w.source, w.target, w.count) for w in d.work_list] == [("b.core", "o.core", 1), ("o.core", "b.core", 3)]
def test_empty_context_is_reported() -> None: ...  # context "typo" matching nothing -> d.empty_contexts == ["typo"]
def test_target_json_ignores_table_order() -> None: ...  # same contexts in a different order -> equal target_json
def test_distance_needs_edges() -> None: ...       # na["distance"] == "missing capability: edges"
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on `core.parse_target`.
- [ ] **Step 3: Implement** the target section.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: target matching and distance"` (add files)

---

### Task 6: Domain signals

**Files:**
- Modify: `$T/core.py` (signals section)
- Test: `tests/assess/test_signals.py`

**Interfaces:**
- Consumes: `Model`, `Target`, `assign_units` (Task 5).
- Produces:
  - `STOP_TERMS: frozenset[str]`, the 21 words of spec 6.2 item 5
  - `split_terms(name: str) -> list[str]`: split on `_`, then each part with `re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")`; lower-case; keep length ≥ 3 and not in `STOP_TERMS`; order kept, duplicates removed.
  - `unit_terms(unit: Unit) -> frozenset[str]`: union over its type names
  - `ScatteredTerm(term: str, groups: list[str])`, `TermSpread(distinct: int, scattered: list[ScatteredTerm])`; `term_spread(model, na) -> TermSpread | None`: scattered = present in ≥ 3 groups; sorted by term. Needs `types`.
  - `Richness(data_only_share: float | None, model_types: int, service_types: int)`; `model_richness(model, na) -> Richness | None`: share over types in model-like units, `None` when there are none. Needs `types`, `data_only`, `layer_hints`.
  - `Entanglement(share: float | None, units: list[str], refs: int)`; `framework_entanglement(model: Model, target: Target | None, na: NotApplicable) -> Entanglement | None`. The scope is model-like units without a target (needs `framework_refs`, `layer_hints`), and units in non-`generic` contexts with a target (needs `framework_refs`). `units` = scope units with refs, sorted; `refs` = number of (unit, ref) pairs in scope; `share` = len(units) / len(scope), `None` for an empty scope.
  - `Escapes(total: int, per_kloc: float | None, by_kind: dict[str, int])`; `escape_totals(model, na) -> Escapes | None`: `per_kloc = total * 1000 / total loc`, `None` when loc is 0. Needs `escapes`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("name,terms", [("OrderLine", ["order", "line"]), ("HTTPServerError", ["http", "server", "error"]),
    ("order_line_item", ["order", "line", "item"]), ("OrderService", ["order"]), ("ID", []), ("Base64Encoder", ["encoder"])])
def test_split_terms(name: str, terms: list[str]) -> None: ...
def test_scattered_needs_three_groups() -> None: ...   # "order" in 3 groups scattered, "line" in 2 not; distinct == 2
def test_model_richness() -> None: ...                 # 3 of 4 model-like types data-only -> 0.75; service_types == 2
def test_richness_share_none_without_model_types() -> None: ...
def test_entanglement_without_target() -> None: ...    # 2 of 4 model-like units with refs -> share 0.5, refs counts pairs
def test_entanglement_with_target_skips_generic() -> None: ...  # generic-context unit with refs excluded from scope
def test_escape_totals() -> None: ...                  # loc 500+500, ANY 2 + CAST 1 -> total 3, per_kloc 3.0, merged by_kind
@pytest.mark.parametrize("missing,metric", [("types", "terms"), ("data_only", "richness"), ("layer_hints", "richness"),
    ("framework_refs", "framework"), ("escapes", "escapes")])
def test_not_applicable_per_capability(missing: str, metric: str) -> None: ...  # na[metric] == f"missing capability: {missing}"
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on `core.split_terms`.
- [ ] **Step 3: Implement** the signals section.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: domain signals"` (add files)

---

### Task 7: Candidate contexts

**Files:**
- Modify: `$T/core.py` (clustering section)
- Test: `tests/assess/test_clusters.py`

**Interfaces:**
- Consumes: `unit_terms` (Task 6), `Model`.
- Produces:
  - `MAX_SWEEPS = 50`
  - `cluster_weights(model: Model) -> dict[str, dict[str, float]]`: symmetric; `w(u, v) = deps(u→v) + deps(v→u) + 2 × jaccard(terms(u), terms(v))`, the term part only where they share a term. Edges are ignored without `edges` and terms without `types`. Only positive weights are stored.
  - `propagate_labels(unit_ids: Sequence[str], weights: dict[str, dict[str, float]]) -> dict[str, str]`: spec 6.3. Each unit starts with its own id as label. Sweep units in sorted order, updating in place: a unit with neighbours takes the label with the highest summed neighbour weight, ties broken by the smallest label. Stop when a sweep changes nothing, or after `MAX_SWEEPS` sweeps.
  - `merge_singletons(labels: dict[str, str], weights: dict[str, dict[str, float]]) -> dict[str, str]`: a unit alone in its label that has neighbours takes the label of the neighbouring cluster with the highest summed weight (ties: smallest label). Units without neighbours keep their label.
  - `Cluster(name: str, terms: list[str], members: list[str], cohesion: float | None)`, `Clusters(clusters: list[Cluster], unclustered: list[str], separable: bool)`
  - `cluster_units(model, na) -> Clusters | None`. Isolated units (no neighbours) are `unclustered`. Term score = `tf × ln(n_clusters / clusters containing term)`, where tf counts the member types whose name yields the term. `terms` = top three by score descending, then term. `name` = `"-".join(terms)`, or the smallest member id when there are no terms. `cohesion` = summed counts of edges with both ends inside / summed counts of edges touching the cluster (`None` if none). Clusters sorted by first member. `separable` = more than one cluster. Not applicable (`missing capability: edges, types`) only when both capabilities are missing.

- [ ] **Step 1: Write the failing tests**

```python
def test_two_obvious_clusters() -> None: ...        # o.a,o.b,o.c types Order*, edges among them; i.a,i.b types Invoice*;
                                                    # one edge o.a->i.a -> members [["i.a","i.b"],["o.a","o.b","o.c"]]
def test_shuffled_input_same_clusters() -> None: ...  # raw units and edges reversed -> identical Clusters
def test_merge_singletons_heaviest_neighbour() -> None:
    labels = {"a": "A", "b": "A", "c": "C", "d": "D", "x": "X"}
    weights = {"x": {"a": 1.0, "c": 2.0}, "a": {"x": 1.0}, "c": {"x": 2.0}}
    assert core.merge_singletons(labels, weights)["x"] == "C"
def test_isolated_units_unclustered() -> None: ...
def test_single_cluster_not_separable() -> None: ...
def test_naming_uses_tf_idf() -> None: ...          # shared term "line" ranks below the cluster-specific term
def test_cohesion() -> None: ...                    # 2 internal edges, 1 outgoing -> 0.6667 (pytest.approx(2/3))
def test_terms_only_without_edges() -> None: ...
def test_edges_only_without_types() -> None: ...
def test_not_applicable_without_edges_and_types() -> None: ...
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on `core.cluster_weights`.
- [ ] **Step 3: Implement** the clustering section.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: deterministic candidate contexts"` (add files)

---

### Task 8: Scorecard, assessment and `analyse`

**Files:**
- Modify: `$T/core.py` (scorecard, assessment, rendering, command line)
- Test: `tests/assess/test_analyse.py`

**Interfaces:**
- Consumes: every metric function from Tasks 4–7, `load_model`, `load_target`, `target_json`.
- Produces:
  - `BOUNDS: dict[str, tuple[float, float, float, float, float]]`, upper bounds for scores 5…1, from spec 6.4: `boundaries (0, .05, .15, .30, .50)`, `language (.05, .10, .20, .30, .45)`, `model_richness (.20, .35, .50, .65, .80)`, `framework_isolation (0, .10, .25, .50, .75)`, `type_safety (0, 1, 3, 6, 10)`
  - `score(value: float | None, bounds: tuple[float, float, float, float, float]) -> int | None`: 5 if `value <= bounds[0]`, … 1 if `value <= bounds[4]`, else 0.
  - `Scorecard(boundaries, language, model_richness, framework_isolation, type_safety)`, all `int | None`. Boundaries with a target = `into_internals` total / all edge counts. Without a target = share of units whose group is in a group cycle, capped at 4. Language = scattered / distinct. Richness = `data_only_share`. Framework = `Entanglement.share`. Type safety = `per_kloc`. A `None` input yields `None` and `na["scorecard.<dim>"]`.
  - `Ratchet(unit_cycle_members, edges_into_internals, escapes, framework_refs_non_generic, unassigned_units)`, all `int | None`. `edges_into_internals`, `framework_refs_non_generic` and `unassigned_units` are `None` without a target (see the spec correction under Self-review notes).
  - `Summary(units: int, loc: int, groups: int, edges: int, skipped: int)`
  - `Assessment` frozen dataclass with fields, in this order: `language, capabilities, not_applicable, summary, layout, unit_cycles, group_cycles, hubs, coupling, churn, terms, richness, framework, escapes, clusters, target, distance, scorecard, ratchet`
  - `assess(model: Model, target: Target | None, churn_cwd: Path | None) -> Assessment` (`churn_cwd` None → `na["churn"] = "not requested"`; no target → `na["distance"] = "no target"`)
  - `assessment_json(a: Assessment) -> dict[str, Json]`: `{"schema": RESULT_SCHEMA}` plus each field by name; dataclasses become objects, frozensets sorted lists, floats `round(x, 4)`, `target` via `target_json`.
  - `render_markdown(a: Assessment) -> str`. Headings in this order: `# Migration assessment`, `## Summary`, `## Scorecard`, `## Recommendation`, `## Layout`, `## Cycles`, `## Hubs`, `## Churn`, `## Scattered terms`, `## Candidate contexts`, `## Hotspot findings`, `## Contexts`, `## Distance to target`, `## Work list`, `## Slices`. The human sections (Recommendation, Hotspot findings, Contexts, Slices) contain only `<!-- human: see references/report-template.md -->`. Under the title, list the capabilities, and `Missing capabilities: …` when any are missing. A not-applicable section reads `n/a: <reason>`. A non-separable result reads `No separable clusters found.` Empty contexts are listed under Distance to target.
  - `main(argv: list[str]) -> int` with `argparse` subcommands. `analyse MODEL --out-dir DIR [--target FILE] [--churn]` writes `DIR/assessment.json` and `DIR/assessment.md`, creating `DIR`. `ModelError`/`TargetError` → message on stderr, exit 2. `--churn` uses `Path.cwd()`. `compare` is added in Task 9.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("dim", sorted(core.BOUNDS))
@pytest.mark.parametrize("i", range(5))
def test_score_at_every_bound(dim: str, i: int) -> None:
    b = core.BOUNDS[dim]
    assert core.score(b[i], b) == 5 - i
    assert core.score(b[i] + 1e-9, b) == 4 - i
def test_score_none() -> None: assert core.score(None, core.BOUNDS["language"]) is None
def test_boundaries_capped_without_target() -> None: ...   # no group cycles -> 4, not 5
def test_ratchet_without_target() -> None: ...             # only unit_cycle_members and escapes set
def test_assessment_json_keys() -> None: ...               # exact key set: "schema" + the 19 field names
def test_analyse_writes_both_files(tmp_path: Path) -> None: ...  # exit 0; md contains every heading above, in order
def test_analyse_is_deterministic(tmp_path: Path) -> None: ...   # same model with units/edges reversed -> identical json bytes
def test_analyse_overlap_exits_2(tmp_path, capsys) -> None: ...  # stderr names the unit and both contexts
def test_analyse_bad_schema_exits_2(tmp_path, capsys) -> None: ...
def test_markdown_marks_not_applicable(tmp_path: Path) -> None: ...  # no edges -> "n/a: missing capability: edges",
                                                                     # "Missing capabilities: edges"
def test_markdown_reports_no_separable_clusters() -> None: ...
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on `core.BOUNDS`.
- [ ] **Step 3: Implement**, with `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`.
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: scorecard, assessment output and analyse command"` (add files)

---

### Task 9: Ratchet (`compare`)

**Files:**
- Modify: `$T/core.py` (ratchet section, `compare` subcommand)
- Test: `tests/assess/test_compare.py`

**Interfaces:**
- Consumes: `assessment_json` shape (Task 8): `schema`, `target`, `ratchet`.
- Produces:
  - `RATCHET_METRICS = ("unit_cycle_members", "edges_into_internals", "escapes", "framework_refs_non_generic", "unassigned_units")`; `TARGET_DEPENDENT = frozenset({"edges_into_internals", "framework_refs_non_generic", "unassigned_units"})`
  - `compare(baseline: object, current: object) -> tuple[int, str]` (exit code, report text). A schema other than `RESULT_SCHEMA` on either side → `(2, "baseline schema <x>, current schema <y>")`. When targets differ (including one side `null`), the report's first line is `targets differ: checking target-independent metrics only` and target-dependent rows are `n/a`. Report is a table with columns `metric baseline current delta status`; status is `ok` (equal), `progress` (decreased), `INCREASED`, or `n/a` (either side `null`, or skipped). Exit 1 if any row is `INCREASED`.
  - `main`: `compare --baseline FILE --current FILE` prints the report; unreadable or non-JSON file → stderr, exit 2.

- [ ] **Step 1: Write the failing tests** (helper `result(ratchet: dict[str, int | None], target: dict[str, object] | None = None) -> dict[str, object]` in the test file)

```python
def test_increase_fails() -> None:     # escapes 3 -> 4: code 1, row "escapes ... INCREASED"
def test_equal_passes() -> None:       # code 0, all rows "ok"
def test_decrease_is_progress() -> None:   # code 0, row "progress"
def test_schema_mismatch() -> None:    # code 2, text names both schema strings
def test_differing_targets_skip_target_dependent() -> None:
    # edges_into_internals 1 -> 9 with different targets: code 0, first line "targets differ: ...", row n/a
def test_baseline_without_target() -> None:   # baseline target None, current set: same as differing
def test_null_metric_is_not_applicable() -> None: ...
def test_cli(tmp_path, capsys) -> None: ...   # files on disk: 0/1 exit codes; missing file -> 2
```

- [ ] **Step 2: Run** TEST. Expected: FAIL on `core.compare`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** TEST, LINT, TYPES. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: compare ratchet"` (add files)

---

### Task 10: End-to-end on a legacy layout

**Files:**
- Create: `tests/assess/legacy.py` (`LEGACY_TREE: dict[str, str]`, `SLICE_TREE: dict[str, str]`, `TARGET_TOML: str`)
- Test: `tests/assess/test_end_to_end.py`

**Interfaces:**
- Consumes: both command lines only, run with `subprocess.run([sys.executable, <tool>, ...], cwd=tmp_path)`: extractor on `src`, then `core.py analyse` (with `--target target.toml`), then `core.py compare`.

**Legacy fixture** under `src/shop/`, no `__init__.py` anywhere, every function fully annotated, under 300 lines in total. Each internal import is one `from <module> import <Name>` statement:

| Module | Classes | Imports |
|---|---|---|
| `models/base.py` | `BaseModel` (fields only) | `sqlalchemy`, `shop.utils.money` |
| `models/order.py` | `Order`, `OrderLine` (fields only) | `sqlalchemy`, `shop.models.base` |
| `models/invoice.py` | `Invoice`, `InvoiceLine` (fields only) | `sqlalchemy`, `shop.models.base` |
| `services/checkout.py` | `OrderService` (one method) | `shop.models.order`, `shop.models.base`, `shop.utils.money` |
| `services/billing.py` | `InvoiceService` (one method with one parameter annotated `Any`, from `from typing import Any`) | `shop.models.invoice`, `shop.models.order`, `shop.services.checkout`, `shop.utils.money` |
| `views/orders.py` | `OrderView` (one method; one line ending `# type: ignore[attr-defined]`) | `flask`, `shop.services.checkout`, `shop.models.order` |
| `views/invoices.py` | `InvoiceView` (one method) | `flask`, `shop.services.billing`, `shop.models.invoice` |
| `utils/money.py` | `Money` (one method) | `shop.models.base` |

`TARGET_TOML`: `ordering` (core) units `shop.models.order*`, `shop.services.checkout*`, `shop.views.orders*`, public `shop.services.checkout`; `billing` (supporting) units `shop.models.invoice*`, `shop.services.billing*`, `shop.views.invoices*`, `shop.billing*`, public `shop.services.billing`, `shop.billing.api`.

**Slice fixture** (`SLICE_TREE`): the legacy tree with `models/invoice.py`, `services/billing.py` and `views/invoices.py` moved to `billing/invoice.py`, `billing/api.py` and `billing/views.py`. Their internal imports point at the new modules, and `billing/api.py` drops its `shop.models.order` import. The `Any` and the framework imports stay.

The expected values below were derived by hand from spec sections 6–7. If the implementation disagrees, recheck the arithmetic against the spec before changing either side, and report the disagreement in the task report.

- [ ] **Step 1: Write the failing tests**

```python
def test_legacy_assessment(tmp_path: Path) -> None:
    a = run_analyse(tmp_path, LEGACY_TREE, target=True)      # returns parsed assessment.json
    assert a["layout"] == "technical layering"
    assert a["unit_cycles"] == [["shop.models.base", "shop.utils.money"]]
    assert a["group_cycles"] == [["shop.models", "shop.utils"]]
    assert a["hubs"][0] == {"id": "shop.models.base", "fan_in": 4}
    assert [s["term"] for s in a["terms"]["scattered"]] == ["invoice", "order"] and a["terms"]["distinct"] == 4
    clusters = {c["name"]: c["members"] for c in a["clusters"]["clusters"]}
    assert clusters["order-line"] == ["shop.models.order", "shop.services.checkout", "shop.views.orders"]
    assert clusters["invoice-line"] == ["shop.models.invoice", "shop.services.billing", "shop.views.invoices"]
    assert clusters["money"] == ["shop.models.base", "shop.utils.money"]
    assert a["distance"]["unassigned"] == ["shop.models.base", "shop.utils.money"]
    assert a["distance"]["pairs"] == [{"source": "billing", "target": "ordering", "via_public": 1, "into_internals": 1}]
    assert a["scorecard"] == {"boundaries": 3, "language": 0, "model_richness": 0, "framework_isolation": 1, "type_safety": 0}
    assert a["ratchet"] == {"unit_cycle_members": 2, "edges_into_internals": 1, "escapes": 3,
                            "framework_refs_non_generic": 4, "unassigned_units": 2}
def test_legacy_without_target(tmp_path: Path) -> None:
    a = run_analyse(tmp_path, LEGACY_TREE, target=False)
    assert a["scorecard"]["boundaries"] == 1 and a["scorecard"]["framework_isolation"] == 0
def test_extraction_is_reproducible(tmp_path: Path) -> None: ...   # two extractor runs -> identical model.json bytes
def test_slice_passes_then_regression_fails(tmp_path: Path) -> None:
    # compare(legacy, slice) -> exit 0, edges_into_internals row "progress" (1 -> 0)
    # slice tree + "from shop.models.order import Order" in billing/api.py -> compare(slice, regression) exit 1, "INCREASED"
```

- [ ] **Step 2: Run** TEST. Expected: the new tests fail only where the fixture is still incomplete. Once `legacy.py` matches the table they should pass against Tasks 1–9. Any other failure is a bug in an earlier task: fix it there, with a unit test.
- [ ] **Step 3: Write** `legacy.py` to the table.
- [ ] **Step 4: Run** TEST, LINT. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "assess: end-to-end legacy layout and slice"` (add files)

---

### Task 11: The skill documents

**Files:**
- Create: `skills/assessing-domain-migration/SKILL.md`
- Create: `skills/assessing-domain-migration/references/scorecard.md`, `layout-patterns.md`, `migration-playbook.md`, `report-template.md`
- Create: `$T/EXTRACTORS.md`

Load `superpowers:writing-skills` and `domain-powers:defining-documentation-language` first.

- [ ] **Step 1: Write `SKILL.md`**. Frontmatter `name: assessing-domain-migration`, description `Use when deciding whether an existing codebase should move to a domain-driven layout, planning that move, or reviewing a change made during one`. Body sections:
  - **Overview** with the core principle "measure first, then decide".
  - **The Iron Law** block, verbatim from spec 8: no migration plan without a measured baseline and a target the human partner has agreed, and no big-bang rewrite.
  - **Phases**: the spec 8 table, with the two checkpoints (contexts agreed, decision made).
  - **Slices**: spec 8.1.
  - **Running the tools**: run from the project root; first check for generated or vendored code and pass `--exclude`; pick extractors from `tools/EXTRACTORS.md`; exact `core.py analyse` and `compare` commands with `--out-dir docs/domain/migration`; renaming to `assessment-YYYY-MM-DD.md` and `baseline.json` in phase 7.
  - **When the tools can't help**: the agent-facing rows of spec 10 (no extractor for a language; skipped files; no separable clusters).
  - **Red flags** table: "the numbers look fine, skip reading hotspots", "we'll agree contexts as we go", "one slice for everything", "refresh the baseline to make the gate pass".
  - Hand-offs to `domain-powers:modeling-the-domain` (phase 3), `superpowers:writing-plans` (phase 6) and `domain-powers:quality-gates` (phase 7).
  - The file names no language syntax or tools.
- [ ] **Step 2: Write the references.**
  - `scorecard.md`: the spec 6.4 table, what each dimension measures and needs, the Boundaries cap without a target, how *n/a* reads.
  - `layout-patterns.md`: recognising technical layering, framework apps / feature packages and mixed layouts from the report, and for each, how its units usually map onto contexts.
  - `migration-playbook.md`: slices, warn-then-strict boundaries (exceptions recorded, then shrunk to zero), re-export shims, `api` facades, anti-corruption layers for legacy callers, and the ordering rule. Point to `domain-powers:quality-gates` (brownfield) for the language's exception lists.
  - `report-template.md`: what to write in each human section (Recommendation: *migrate*, *migrate the core context only* or *don't migrate*, with reasons; Hotspot findings: each with `file:line`; Contexts: link the glossary and context map; Slices: ordered list with each slice's contexts and units).
- [ ] **Step 3: Write `EXTRACTORS.md`**: the contract for new extractors (spec 5.1–5.3, with the schema id, field table, hint vocabulary and groups, command line, exit codes, determinism, and "undeclared capability means not applicable"). Add a **Shipped extractors** table: `python`, detected by `*.py` files or `pyproject.toml` / `setup.py` / `setup.cfg`, command `python3 <skill>/tools/extractors/python.py src --out model.json`.
- [ ] **Step 4: Verify.** Run the vocabulary scan from `CLAUDE.md` (it copies `skills`), with `~/.local/bin/python3.13` in place of `python3`. Expected: `0 findings`. Then `claude plugin validate .`. Expected: `Validation passed` (the existing README install-line warning is acceptable).
- [ ] **Step 5: Commit** `git add skills/assessing-domain-migration && git commit -m "assess: skill and references"`

---

### Task 12: Plugin integration and release

**Files:**
- Modify: `skills/defining-documentation-language/references/language-seed.md` (Work structure table)
- Modify: `skills/quality-gates/SKILL.md`, `skills/quality-gates/references/check.sh`, `examples/sample-shop/scripts/check.sh`
- Modify: `agents/domain-reviewer.md`
- Modify: `skills/using-domain-powers/SKILL.md`
- Modify: `README.md`, `.claude-plugin/plugin.json`, `CLAUDE.md`

- [ ] **Step 1: Vocabulary.** Add the row `| slice | One unit of migration work that moves one context, or part of one, behind its boundary and ends with every gate green | A plan (each slice gets its own plan) | migration step, increment, migration phase |` after `fix wave`.
- [ ] **Step 2: Gate 8.** In `quality-gates/SKILL.md`, add the row `| 8 | Migration | extractor, then core.py analyse, then core.py compare (when docs/domain/migration/baseline.json exists) | No ratchet metric grew since the baseline |`. Add `migration ✓ (0 increased)` to the evidence line. In setup step 3, also vendor `skills/assessing-domain-migration/tools/` as `scripts/assess/`. In the template `check.sh`, after the language gate, add the block below. Then copy the template over `examples/sample-shop/scripts/check.sh`, which also restores its missing language gate.

```bash
ASSESS="${ASSESS:-scripts/assess}"
MIGRATION="docs/domain/migration"
migration_check() {
  local out target=()
  out="$(mktemp -d)"
  [ -f "$MIGRATION/target.toml" ] && target=(--target "$MIGRATION/target.toml")
  python3 "$ASSESS/extractors/python.py" "$SRC" --out "$out/model.json" \
    && python3 "$ASSESS/core.py" analyse "$out/model.json" --out-dir "$out" "${target[@]}" \
    && python3 "$ASSESS/core.py" compare --baseline "$MIGRATION/baseline.json" --current "$out/assessment.json"
}
if [ -f "$MIGRATION/baseline.json" ]; then
  gate migration migration_check
fi
```

  The commands are chained with `&&` because `set -e` does not apply inside an `if` condition.
- [ ] **Step 3: Reviewer migration mode.** Add a `## Migration mode` section to `agents/domain-reviewer.md`:
  - Inputs: `docs/domain/migration/baseline.json`, `target.toml`, and the current slice from the latest assessment report.
  - Procedure: produce a current assessment with the tools, run `compare`, and paste its table under Tool evidence as `- migration: <table>`.
  - Checks: the diff touches only the current slice's contexts and units; exception lists (`ignore_imports`, legacy overrides, allow comments) shrink and never grow; no new re-export shims; the baseline is refreshed only when a slice ends.
  - Severities: a ratchet increase is Critical; a new shim or a change outside the slice is Important.
- [ ] **Step 4: Routing and README.** Add the routing row to `using-domain-powers/SKILL.md`: `| Assessing a codebase for a DDD migration, or reviewing a migration change | domain-powers:assessing-domain-migration |`. In `README.md`:
  - Add an **Assessing a migration** section (what the tools measure, the seven phases in one line each, the baseline and the gate).
  - Add a **Language packs** section with the spec 3 convention.
  - Change "seven gates (…)" to "eight gates (…, migration)".
- [ ] **Step 5: Release.** Set `"version": "0.3.0"` in `plugin.json`. In `CLAUDE.md`, set Current state to v0.3.0 with nine skills, the assessment tools, gate 8 and the reviewer migration mode; move "Migration assessment skill" off Queued work.
- [ ] **Step 6: Verify, fresh**: TEST, LINT, TYPES; `claude plugin validate .`; the vocabulary scan from `CLAUDE.md` (with Python 3.13); and the sample shop gates in a Python 3.13 venv (`./scripts/check.sh`). Expected: every command passes; the sample shop prints `Gates: format ✓ lint ✓ types ✓ boundaries ✓ escapes ✓ tests ✓` with no migration gate (it has no baseline); the scan reports `0 findings`.
- [ ] **Step 7: Commit** `git add -A && git commit -m "domain-powers v0.3.0: migration assessment"`

---

## Self-review notes

- **Spec correction:** spec section 7 says "the last three [ratchet metrics] need a target", but its list puts total escapes third from last, and escapes need no target. This plan treats cross-context edges into internals, framework refs in non-generic contexts and unassigned units as the target-dependent three, which matches what each metric measures. The spec text is corrected in the same commit as this plan.
- **Decisions the spec leaves open, fixed here:**
  - unit `path` relative to the working directory, with churn via `git log --relative`
  - root-package detection, and skipped directories
  - `Meta` / `Config` nested classes count as data-only
  - edge and ratchet counts are summed import counts
  - the target-dependent framework scope includes `supporting` contexts
  - one model per `analyse` run
  - report headings and placeholders
- **Vocabulary:** the `Interfaces:` label in each task is the superpowers plan template's. The seed lists `interface` as an avoided synonym of *port*. `docs/` is not scanned, so this produces no finding; whether to add the label to Allowed phrases is a question for the language-pack spec.
