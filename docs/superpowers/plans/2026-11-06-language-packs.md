# Language Packs and the Rust Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split domain-powers into an agnostic core plus language packs, move Python into its pack unchanged, and ship a Rust pack (guard, extractor, gates, skill variants, example).

**Architecture:** `scripts/domain_guard.py` keeps the hook formats, scan mode and Markdown checks, and dispatches source files by suffix to `scripts/languages/<lang>.py`. Extractors in `scripts/assess/extractors/` import the same pack modules, so escape counts match the guard. Skills keep agnostic rules in `SKILL.md` and language detail in `languages/<lang>.md`.

**Tech Stack:** Python 3.11+ standard library, pytest, ruff, mypy strict; Rust example uses cargo, clippy, rustfmt, cargo-deny, proptest.

**Spec:** `docs/superpowers/specs/2026-11-06-language-packs-design.md`

## Global Constraints

- Scripts: Python 3.11+ standard library only; pass `ruff format --check`, `ruff check` (`ruff.toml`) and `mypy --strict`.
- Skill descriptions start with "Use when…" and never summarise the workflow.
- Documentation uses `docs/language.md` terms; never `stage` for a phase, never `interface` for a port.
- Agnostic files never name a language's syntax or tools.
- Preserve Claude Edit/Write/MultiEdit and Codex `apply_patch` payload handling.
- Version 0.4.0 in `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`.
- Projects vendor `domain_guard.py`, `languages/`, `assess/` as `scripts/domain-powers/`.

## Review Focus

- A Rust file mid-edit (unterminated string, unbalanced braces) must not crash the guard: Task 2 test `test_lexer_unterminated_string_masks_to_eof`.
- Lifetimes (`'a`) must not be lexed as char literals and swallow code: Task 2 test `test_lexer_lifetime_is_not_char`.
- `#[allow(...)]` inside `#[cfg(test)] mod tests` is still `IGNORE`, but `unwrap()` there is not reported: Task 3 test `test_cfg_test_module_reports_only_ignore`.
- A local `mod http;` used as `http::x` in a domain is not a framework dependency: Task 3 test `test_local_module_shadows_forbidden_crate`.
- Python behaviour unchanged after the move: the full existing suite (`tests/`) passes in Task 1 without assertion changes.

---

### Task 1: Agnostic guard core, Python pack, tools moved

**Files:**
- Create: `scripts/languages/__init__.py`, `scripts/languages/python.py`
- Modify: `scripts/domain_guard.py` (keep hook, scan, Markdown; delegate source analysis)
- Move: `skills/assessing-domain-migration/tools/{core.py,EXTRACTORS.md,extractors/python.py}` → `scripts/assess/…`
- Modify: `scripts/assess/extractors/python.py` (drop duplicated escape and framework lists; import `languages.python`)
- Modify: `tests/assess/conftest.py` (tool path), `CLAUDE.md` verify commands, `skills/defining-documentation-language/references/language-seed.md` and `docs/language.md` (term *language pack*)

**Interfaces:**
- Produces in `languages/__init__.py`:
  - `Finding(path: Path, line: int, code: str, message: str)` frozen dataclass with `render()`; `ALLOW_RE`
  - `class LanguagePack(Protocol)`: `name: str`, `suffixes: tuple[str, ...]`, `analyse(path: Path, source: str) -> list[Finding]`, `expand_changed(source: str, lines: set[int]) -> set[int]`
  - `pack_for(path: Path) -> LanguagePack | None`, `SOURCE_SUFFIXES: tuple[str, ...]`
- Produces in `languages/python.py`: `PACK`, `escape_lines(source: str, tree: ast.Module, *, is_test: bool) -> dict[str, list[int]]` (kind → line numbers before justification), `framework_refs(tree: ast.Module) -> list[str]`, `DEFAULT_DOMAIN_FORBIDDEN`
- `domain_guard.py` keeps `main(argv)`, `check_markdown`, `load_vocabulary`, `patch_edits`, `snippet_lines`; test_codex.py must still pass unchanged.

- [ ] **Step 1:** Move the tools with `git mv`; point `tests/assess/conftest.py` at `scripts/assess` and add `scripts` to `sys.path`.
- [ ] **Step 2:** Extract the Python rules into `languages/python.py`; `domain_guard.analyse(path, source)` becomes `pack_for(path).analyse(...)`; `declaration_lines` becomes `PythonPack.expand_changed`.
- [ ] **Step 3:** Python extractor computes escapes from `escape_lines` plus the shared justification rule, and framework refs from `framework_refs`. Extractors insert `Path(__file__).resolve().parents[2]` on `sys.path` to import `languages`.
- [ ] **Step 4:** Run `uv run --python 3.13 --with pytest pytest tests -q`. Expected: 170 passed, no assertion edited.
- [ ] **Step 5:** Lint, mypy strict over `scripts/*.py scripts/languages/*.py scripts/assess/*.py scripts/assess/extractors/*.py`; commit `packs: agnostic guard core and Python pack`.

### Task 2: Rust lexer and path resolution

**Files:**
- Create: `scripts/languages/rust.py` (lexer and `use` parsing part), `tests/guard/test_rust_lexer.py`, `tests/guard/conftest.py`

**Interfaces:**
- Produces: `mask(source: str) -> str` (comments, string, raw string, byte string and char literal contents become spaces; newlines kept; same length)
- `use_paths(masked: str) -> list[tuple[int, list[str]]]` (line, path segments; groups expanded, `as` renames dropped, `*` dropped, `self` in a group means the prefix)
- `qualified_paths(masked: str) -> list[tuple[int, list[str]]]` (path expressions `a::b` not preceded by `::`, excluding `use` lines)
- `test_ranges(masked: str) -> list[tuple[int, int]]` (line ranges of `#[cfg(test)]` items)
- `resolve(segments: list[str], crate: str, module: list[str], *, is_mod_rs: bool) -> list[str]` (`crate`/`self`/`super` to absolute, rooted at the crate name)

- [ ] **Step 1:** Write tests: `test_lexer_masks_line_and_nested_block_comments`, `test_lexer_masks_strings_raw_strings_and_chars`, `test_lexer_lifetime_is_not_char` (`fn f<'a>(x: &'a str) -> &'a str { x.unwrap() }` keeps `unwrap` visible), `test_lexer_unterminated_string_masks_to_eof`, `test_use_tree_groups_and_renames` (`use crate::a::{b::{C, D as E}, self};` → `crate a b C`, `crate a b D`, `crate a`), `test_qualified_paths_skip_use_lines`, `test_cfg_test_range`, `test_resolve_super_and_self`.
- [ ] **Step 2:** Run; expect import failure. Implement; run; expect pass.
- [ ] **Step 3:** Commit `rust: lexer and path resolution`.

### Task 3: Rust guard pack

**Files:**
- Modify: `scripts/languages/rust.py`, `scripts/languages/__init__.py` (register), `scripts/domain_guard.py` (`.rs` accepted in hook and scan)
- Create: `tests/guard/test_rust_guard.py`

**Interfaces:**
- Produces: `RustConfig` (`project_root`, `contexts`, `shared`, `public_module`, `domain_forbidden`), `load_config(start: Path) -> RustConfig`, `locate(path: Path, cfg: RustConfig) -> RustLocation` (`crate`, `module: list[str]`, `context`, `layer`, `is_test`), `escape_lines(masked: str, test_ranges) -> dict[str, list[int]]`, `framework_refs(masked: str, local_modules: set[str]) -> list[str]`, `DEFAULT_DOMAIN_FORBIDDEN`, `PACK`.

- [ ] **Step 1:** Write tests (files built in `tmp_path` with a workspace `Cargo.toml` holding `[workspace.metadata.domain-powers] contexts = ["ordering", "billing"]`, crates `crates/ordering`, `crates/billing`, `crates/shared-kernel`):
  - each code: `UNSAFE` (`unsafe { }`, `unsafe fn`), `PANIC` (`.unwrap()`, `.expect("x")`, `todo!()`), `CAST` (`x as u32`, `transmute`), `ANY` (`dyn Any`), `IGNORE` (`#[allow(dead_code)]`)
  - `test_allow_comment_outside_domain` suppresses; `test_allow_comment_inside_domain_rejected` keeps the finding with "not accepted in the domain layer"
  - `test_cfg_test_module_reports_only_ignore`, `test_tests_dir_reports_only_ignore`
  - `test_domain_uses_sqlx_is_domain_dep`, `test_domain_uses_std_fs_is_domain_dep`, `test_domain_uses_shared_kernel_ok`, `test_local_module_shadows_forbidden_crate`
  - `test_application_uses_infrastructure_is_layer`
  - `test_cross_context_internals` (`use billing::domain::Payment;` in ordering) and `test_cross_context_api_ok` (`use billing::api::PaymentRequest;`)
  - `test_single_crate_layout` (`src/ordering/domain/order.rs` using `crate::billing::domain`)
  - `test_package_metadata_config`, `test_no_config_infers_domain_from_dir`
  - `test_hook_edit_on_rs_reports_changed_lines_only` and `test_codex_patch_on_rs` through `domain_guard.py` subprocess
- [ ] **Step 2:** Run; expect failures. Implement; run; expect pass. Run whole suite.
- [ ] **Step 3:** Commit `rust: guard pack`.

### Task 4: Rust extractor

**Files:**
- Create: `scripts/assess/extractors/rust.py`, `tests/assess/test_rust_extractor.py`
- Modify: `scripts/assess/EXTRACTORS.md` (Shipped extractors row)

**Interfaces:**
- Consumes: `languages.rust` (`mask`, `use_paths`, `qualified_paths`, `test_ranges`, `resolve`, `escape_lines`, `framework_refs`).
- Produces: `extract(source_root: Path, *, package: str | None = None, include_tests: bool = False, exclude: Sequence[str] = ()) -> dict[str, Json]`; CLI per contract.

- [ ] **Step 1:** Tests: `test_ids_and_groups_single_crate` (`shop::ordering::order`, group `shop::ordering`), `test_groups_by_crate_in_workspace`, `test_edges_from_use_and_qualified_paths` (counts, `mod` not an edge), `test_types_and_data_only` (plain struct true; struct with `new` and accessor true; struct with a behaviour method false; trait impls ignored), `test_escapes_and_framework_refs`, `test_tests_excluded_by_default`, `test_deterministic_output`, `test_model_accepted_by_core` (`core.parse_model` and `core.assess` run).
- [ ] **Step 2:** Run, implement, run. Commit `rust: assessment extractor`.

### Task 5: Agnostic skills, Python variants, pack cards, reviewer, hooks

**Files:**
- Modify: every `skills/*/SKILL.md` listed in spec section 7, `agents/domain-reviewer.md`, `scripts/pair_skills.py`, `skills/quality-gates/references/check.sh`
- Move: Python references into `skills/<skill>/languages/python.md` (type-driven-design, modeling-aggregates, testing-invariants, designing-boundaries incl. ports-and-adapters, quality-gates incl. pyproject template kept as `languages/python/pyproject-template.toml`)
- Create: `skills/using-domain-powers/languages/python.md` (pack card)

- [ ] **Step 1:** Rewrite each SKILL.md agnostically with a "Language variants" line: "Read `languages/<language>.md` for the project's language (`python`, `rust`)."
- [ ] **Step 2:** `check.sh`: gate order once; `case "$LANG_PACK"` command map; detection from `Cargo.toml`/`pyproject.toml`; `DOMAIN_POWERS` dir default `scripts/domain-powers`.
- [ ] **Step 3:** Reviewer and pair hook made agnostic; reviewer reads the pack card. Run vocabulary check; run `claude plugin validate .`.
- [ ] **Step 4:** Commit `packs: agnostic skills and Python variants`.

### Task 6: Rust skill variants and gate templates

**Files:**
- Create: `skills/{type-driven-design,modeling-aggregates,testing-invariants,designing-boundaries,quality-gates}/languages/rust.md`, `skills/using-domain-powers/languages/rust.md`, `skills/quality-gates/languages/rust/{Cargo-template.toml,deny-template.toml}`

- [ ] **Step 1:** Write the variants per spec section 7; code samples must compile (checked in Task 7 by building the same patterns in the example).
- [ ] **Step 2:** Vocabulary check; commit `rust: skill variants and gate templates`.

### Task 7: Examples, docs, version

**Files:**
- Create: `examples/rust-shop/` (workspace: `shared-kernel`, `ordering`, `billing`, `app`; `deny.toml`; `scripts/check.sh`; vendored `scripts/domain-powers/`; proptest invariant tests)
- Modify: `examples/sample-shop/scripts/` (vendored dir replaces single guard file; check.sh), `README.md`, `CLAUDE.md`, `AGENTS.md`, both plugin manifests

- [ ] **Step 1:** Build the Rust example; `./scripts/check.sh` green. Inject `unwrap()` in `ordering/src/domain` and `use billing::domain` in ordering: the guard scan and clippy/compiler fail; revert.
- [ ] **Step 2:** Refresh sample-shop vendoring; its check.sh green.
- [ ] **Step 3:** README, CLAUDE.md (verify commands, current state), versions. Commit `domain-powers v0.4.0: language packs and Rust`.

### Task 8: Verification and review

- [ ] Run every command in `CLAUDE.md` Verify; build the package archive and confirm `scripts/languages` and `scripts/assess` are in it; whole-branch review; fix wave if needed.
