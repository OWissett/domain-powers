# Language Packs and the Rust Pack: Design

Date: 2026-11-06
Status: Approved (human partner skipped brainstorming questions and asked for the work directly)
Plugin: domain-powers (v0.3.0 → v0.4.0)

## 1. Understanding

**What was asked:** make the skills work for Rust, and separate language-agnostic skills and tools from language-specific ones.

This joins the two queued items in `CLAUDE.md`: the language-pack restructure (apply the convention from the migration-assessment spec, section 3, to everything) and the Rust language pack.

**Calls made without the human partner** (they opted out of questions; each is marked so a reviewer can challenge it):

| Call | Decision |
|---|---|
| Rust analysis technique | A small lexer plus pattern matching in Python 3.11 standard library, like the rest of the plugin. No `syn`, no tree-sitter, no Rust toolchain needed to run the guard or extractor. The compiler, clippy and `cargo deny` give the exact checks in the gates; the guard gives fast feedback on the lines just written. |
| Rust project config | `[workspace.metadata.domain-powers]` or `[package.metadata.domain-powers]` in the nearest `Cargo.toml`. Cargo ignores `metadata` tables, so no extra file is needed. |
| Recommended Rust layout | A Cargo workspace with one crate per context. A context crate exposes only `pub mod api`; its `domain`, `application` and `infrastructure` modules are private, so the compiler enforces cross-context boundaries. A core context may split its domain into its own crate (`<context>-domain`) so Cargo enforces domain purity too. A single crate with one module per context is also supported by the guard. |
| `serde` in a Rust domain | Forbidden by default, for the same reason pydantic is forbidden in a Python domain: deriving `Deserialize` builds a value without going through its parsing constructor. DTOs in infrastructure derive serde and parse into domain types. |
| Rust escape kinds | `UNSAFE`, `PANIC`, `CAST`, `ANY`, `IGNORE` (section 5.3). Rust has no `UNTYPED`. |
| Where shared tools live | `scripts/` in the plugin, vendored into a project as one directory, `scripts/domain-powers/`. The assessment tools move from the skill directory to `scripts/assess/` so extractors can share the guard's language packs. |
| Version | v0.4.0. |

**Success criteria:**
1. Every skill reads correctly for a Python or a Rust project; nothing agnostic names a language's syntax or tools.
2. Adding a language means adding files under `languages/` and `extractors/` directories plus one registry line; no agnostic file changes beyond the "shipped" tables.
3. The guard catches Rust type escapes and boundary violations on the lines just written, in Claude Code and Codex payloads, as it does for Python.
4. The Rust extractor produces a model the unchanged `core.py` accepts, and the end-to-end assessment flow works on a Rust tree.
5. A sample Rust workspace passes every Rust gate, and injected violations fail them.
6. All existing tests still pass, so Python behaviour is unchanged.

## 2. Scope

**In scope:** the restructure of skills, guard, assessment tools, gates, reviewer, routing and hooks into an agnostic core plus language packs; the Python pack (moved, not rewritten); the Rust pack; the vocabulary term *language pack*; a Rust example project; tests.

**Out of scope:** a C pack (the convention makes it a later addition); changes to the assessment metrics, scorecard or ratchet; changes to Codex hook wiring beyond file suffixes.

## 3. The convention, applied

Restated from the migration-assessment spec, section 3, with this spec's additions:

- The agnostic part (process, rules, data model, analysis) never names a language's syntax or tools.
- **Documents:** a skill whose guidance depends on the language keeps the agnostic rules in `SKILL.md` and puts each language's patterns, commands and examples in `skills/<skill>/languages/<language>.md`. The skill tells the agent to read the variant for the project's language.
- **Tools:** each language has one module in `scripts/languages/<language>.py` (used by the guard and by that language's extractor) and one extractor in `scripts/assess/extractors/<language>.py`.
- A variant declares what it supports. Anything undeclared is *not applicable*, never zero.
- `skills/using-domain-powers/languages/<language>.md` is the **pack card**: how the language is detected, where its config lives, its guard codes, and the reviewer's language checklist. It is the entry point for each language.

**Language pack** joins the documentation language: "the set of per-language files (pack card, skill variants, guard module, extractor) for one language". Avoid: `language plugin`, `language support module`.

## 4. Layout

```
scripts/
  pair_skills.py                 hook only; never vendored
  domain_guard.py                agnostic guard: hook mode, scan mode, Markdown TERM check, pack dispatch
  languages/
    __init__.py                  Finding, Location, LanguagePack protocol, registry by file suffix
    python.py                    Python pack (moved from domain_guard.py)
    rust.py                      Rust pack
  assess/
    core.py                      unchanged apart from its path
    EXTRACTORS.md                extractor contract; Shipped extractors table gains Rust
    extractors/
      python.py                  uses languages.python for escapes and framework refs
      rust.py                    Rust extractor
skills/<skill>/languages/{python,rust}.md
skills/using-domain-powers/languages/{python,rust}.md   pack cards
examples/sample-shop/            Python example (vendored dir refreshed)
examples/rust-shop/              Rust example workspace
tests/guard/                     guard tests per pack
tests/assess/                    + Rust extractor tests
```

A project vendors `scripts/domain_guard.py`, `scripts/languages/` and `scripts/assess/` as `scripts/domain-powers/`. Both examples do, and `CLAUDE.md` says to refresh them whenever the tools change.

## 5. Guard

### 5.1 Agnostic core (`domain_guard.py`)

Owns everything that is not a language rule: the hook payload formats (Claude Edit, Write, MultiEdit; Codex `apply_patch`), changed-line detection, scan mode, the Markdown vocabulary check, `# domain-powers: allow <reason>` handling (no justification is accepted in a domain layer), and output. It looks up a pack by file suffix and asks it for findings. An unknown suffix is ignored, as now.

### 5.2 Pack protocol

```python
class LanguagePack(Protocol):
    name: str
    suffixes: tuple[str, ...]
    def analyse(self, path: Path, source: str) -> list[Finding]: ...   # loads its own config, locates the file
    def expand_changed(self, source: str, lines: set[int]) -> set[int]: ...  # e.g. multi-line imports
```

Each pack finds its config (`pyproject.toml` or `Cargo.toml`), maps the file to context and layer, and reports findings with the shared codes: `ANY`, `CAST`, `IGNORE`, `UNTYPED`, `DOMAIN-DEP`, `LAYER`, `CROSS-CTX`, plus language-specific codes. The pack exposes the escape detector as a function so the extractor counts exactly what the guard reports. This removes the duplicated detection in the Python extractor.

### 5.3 Rust pack

**Config:**

```toml
[workspace.metadata.domain-powers]
contexts = ["ordering", "billing"]   # context crate names, or module names in a single-crate layout
shared = ["shared_kernel"]
public_module = "api"
domain_forbidden = []                # extra crates or paths, merged with the defaults
```

**Locating a file:** the crate is the nearest `Cargo.toml` with a `[package]` name (hyphens become underscores). The module path comes from the file's position under `src/` (`lib.rs`, `main.rs`, `mod.rs` and `foo.rs` rules). The context is the crate when its name is a listed context, or `<context>_<layer>`; otherwise the first module segment that is a listed context. The layer is the next segment that is `domain`, `application` or `infrastructure`. Without config, the layer is inferred from directory names, as for Python. Files under `tests/`, `benches/` and `examples/`, and lines inside `#[cfg(test)]` items, are test code.

**Paths:** `use` trees (groups, globs, renames, `crate::`, `self::`, `super::`, `::`) and qualified paths in code (`sqlx::query(...)`, `std::fs::read`) are resolved to absolute paths. Comments, strings, raw strings and char literals are masked first.

**Codes:**

| Code | Catches |
|---|---|
| `UNSAFE` | `unsafe` blocks, functions, impls and traits |
| `PANIC` | `.unwrap()`, `.expect(`, `panic!`, `todo!`, `unimplemented!`, `unreachable!` |
| `CAST` | `as` conversions to a primitive numeric type, `transmute` |
| `ANY` | `std::any::Any`, `dyn Any`, `downcast` |
| `IGNORE` | `#[allow(...)]`, `#![allow(...)]`, `#[expect(...)]` |
| `DOMAIN-DEP` | domain using a framework, I/O crate, `std::fs`/`net`/`process`/`env`, or a non-domain module |
| `LAYER` | application using its own context's infrastructure |
| `CROSS-CTX` | a context using another context's internals instead of its `api` |

In test code only `IGNORE` is reported, as for Python. Default forbidden in a domain: `sqlx`, `diesel`, `sea_orm`, `rusqlite`, `postgres`, `tokio_postgres`, `mongodb`, `redis`, `reqwest`, `hyper`, `axum`, `actix_web`, `rocket`, `warp`, `tonic`, `tower`, `tokio`, `async_std`, `serde`, `serde_json`, `aws_sdk_*`, `std::fs`, `std::net`, `std::process`, `std::env`.

**Changed lines:** an edited line inside a multi-line `use` or `fn` signature also selects the line where the item starts, mirroring the Python pack.

## 6. Assessment tools

- `core.py` and `EXTRACTORS.md` move to `scripts/assess/`. Contract unchanged.
- The Python extractor imports `languages.python` for escapes and framework refs.
- **Rust extractor:** units are `.rs` files under each crate's `src/`, with id `crate::module::path`. `root` is the source root given. With one crate (or `--package NAME`), `group` is the crate plus its first module; with several crates, `group` is the crate. Edges come from resolved `use` and qualified paths into other units (longest unit prefix); `mod` declarations are structure, not edges. `types` are `struct`, `enum`, `union` and `trait` declarations at file level. `data_only` is true for a struct, enum or union whose inherent `impl` blocks in the same file hold only constructors (`new`, `default`, `from_*`, `with_*`) and accessors (a body that only returns a field, optionally borrowed or cloned); trait impls do not count, like Python's dunder methods. Escapes and framework refs come from `languages.rust`. Layer hints use the same vocabulary and aliases. Tests (`tests/`, `benches/`, `examples/` directories and `#[cfg(test)]` modules) are excluded by default. All six capabilities are declared.
- Detected by: `*.rs` files or `Cargo.toml`.

## 7. Skills

| Skill | Agnostic `SKILL.md` keeps | `languages/python.md` | `languages/rust.md` |
|---|---|---|---|
| using-domain-powers | routing table, where the domain lives, guard behaviour, red flags; "detect the language, read its pack card" | pack card | pack card |
| type-driven-design | iron law, smell → pattern table in neutral terms, layer rules, checker-complaint loop | Python patterns (existing reference), tool-per-layer table, suppression syntax | newtypes, smart constructors, typestate, enums, `Result`, exhaustive `match`, no serde in domain |
| modeling-aggregates | rules, anemic check | existing Python reference | aggregates with private fields, consuming state transitions, events, repositories as traits |
| testing-invariants | portfolio by layer (neutral), TDD with properties, strategy discipline | Hypothesis (existing reference) | proptest, `proptest-state-machine`, fakes, contract suites as generic test functions |
| designing-boundaries | iron law, shape (neutral), plan additions, ACLs | layout, import-linter, ports and adapters (existing references) | workspace layout, visibility, `cargo deny` bans with wrappers, ports as traits |
| quality-gates | eight gates defined once with what each proves; iron law; brownfield principles; never-do-this | command map, setup, pyproject template, brownfield lists | command map, setup, `Cargo.toml` lints, `deny.toml`, brownfield lists |
| assessing-domain-migration | unchanged process; tool paths move; Rust row in the extractor table | | |
| modeling-the-domain, defining-documentation-language | already agnostic | | |

**Gates, once:**

| # | Gate | Python | Rust |
|---|---|---|---|
| 1 | Format | `ruff format --check .` | `cargo fmt --all --check` |
| 2 | Lint | `ruff check .` | `cargo clippy --workspace --all-targets -- -D warnings` |
| 3 | Types | `mypy` (strict) | `cargo check --workspace --all-targets` |
| 4 | Boundaries | `lint-imports` | `cargo deny check bans` |
| 5 | Escape audit | guard `--scan src` | guard `--scan crates` |
| 6 | Tests | `pytest -q` (Hypothesis `ci` profile) | `cargo test --workspace` (proptest) |
| 7 | Language | guard `--scan docs README.md` | same |
| 8 | Migration | Python extractor, `analyse`, `compare` | Rust extractor, `analyse`, `compare` |

`references/check.sh` defines the gate order once and picks the command map from the project's manifest (`Cargo.toml` → Rust, `pyproject.toml` → Python; `DOMAIN_POWERS_LANGUAGE` overrides).

## 8. Reviewer, routing and hooks

- `domain-reviewer`: description and procedure become agnostic. The checklist keeps the agnostic checks; step 1 reads the pack card for the project's language, whose checklist adds the language checks. Tool commands come from the pack card.
- `using-domain-powers`: description drops "Python"; config line names both manifests.
- `pair_skills.py`: notes drop "Python"; implementer note adds "and the `languages/` variant for the project's language".
- `domain_guard.py` hook mode accepts `.rs` alongside `.py`, `.pyi` and `.md`.
- `plugin.json` and `.codex-plugin/plugin.json`: version 0.4.0; description and keywords name Rust.
- README: language packs section rewritten; guard codes per language; Rust setup.

## 9. Errors and edge cases

| Situation | Behaviour |
|---|---|
| Rust file mid-edit with unbalanced braces or an unterminated string | The lexer masks to end of file; findings on earlier lines still report; no crash |
| `Cargo.toml` unreadable or without the metadata table | Escape checks still run; layers inferred from directory names |
| A module named like a forbidden crate (`mod http;`) | Paths rooted at a module declared in the same file are local, not crate references |
| Macro-generated code | Not seen; the gates (clippy, compiler) cover it |
| Workspace with no crates under the scan root | Extractor exits 0 with no units |

## 10. Testing

- **Existing suite:** passes unchanged apart from import paths (Python behaviour preserved).
- **Guard, Rust pack:** lexer masking (comments, nested block comments, strings, raw strings, chars vs lifetimes); each code; justification outside and inside a domain; `#[cfg(test)]` exclusion; config from workspace and package metadata; context and layer for workspace and single-crate layouts; `use` tree resolution; changed-line expansion; hook payloads (Claude and Codex) on `.rs` files.
- **Rust extractor:** ids, groups, edges, types and `data_only`, escapes, framework refs, tests excluded, determinism, and a run through `core.py analyse`.
- **Example:** `examples/rust-shop` passes every Rust gate; an injected `unwrap` in a domain and a cross-context internals import are caught by the guard and by clippy or the compiler.
- **Quality bar:** ruff format and lint, `mypy --strict` over every script, `claude plugin validate`, the vocabulary check of the plugin's own Markdown.
