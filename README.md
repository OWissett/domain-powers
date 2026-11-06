# domain-powers

Domain-driven design, strong boundaries and type-level guarantees for coding agents working in Python or Rust. Built as a companion to [superpowers](https://github.com/obra/superpowers): superpowers sets *how* the agent works (brainstorm → plan → TDD → review → verify), and domain-powers sets *what good looks like* in the model, its boundaries and its types.

**Requires:** the superpowers plugin, Python ≥ 3.11 on the machine running hooks (for `tomllib`). Target projects use Python ≥ 3.12, or Rust (edition 2021+) with clippy, rustfmt and cargo-deny.

## Codex support

Codex desktop can load the nine skills, a startup routing hook, and a native patch
edit guard through the Codex compatibility manifest. A skills-only installation
also works, with explicit routing and manual guard scans. The full installation
instructions explain hook trust, shared resource paths, updates, and limitations
([Codex installation](.codex/INSTALL.md)).

In Codex, paired skills are read from their files, and a generic subagent can use
the domain-reviewer instructions. There is no dependency on Claude's `Skill` tool
or named-agent registry. Skill pairing remains an agent instruction; the Codex
patch guard runs automatically only when its plugin hooks are installed and trusted.

## How it fits superpowers

| Superpowers phase | domain-powers adds |
|---|---|
| `brainstorming` | **modeling-the-domain**: ubiquitous-language glossary, event-storming-lite, bounded contexts, context map in `docs/domain/` |
| `brainstorming`, `writing-plans`, `writing-skills`, any doc | **defining-documentation-language**: one term per process concept (phase, plan, task, step, batch, round, fix wave, gate…) in `docs/language.md`, seeded to match superpowers |
| `writing-plans` | **designing-boundaries**: context/layer/invariants per task, ports & adapters, ACLs, inside-out task order, contracts before code |
| `test-driven-development` | **type-driven-design**: value objects, distinct ID types, typestate, result types, exhaustive matching, parse-don't-validate |
| | **modeling-aggregates**: small aggregates, root-only mutation, domain events, ID references, idempotent policies |
| | **testing-invariants**: property tests (Hypothesis, proptest) and stateful command sequences per glossary invariant; fakes over mocks; port contract suites |
| `verification-before-completion` | **quality-gates**: eight gates (format, lint, types, boundaries, escape scan, tests, documentation language, migration), with a command map per language, and brownfield ratchets |
| | **assessing-domain-migration**: measure an existing codebase, agree contexts and a target, recommend migrate or not, and ratchet progress slice by slice |
| `requesting-code-review` | **domain-reviewer** agent: language drift, boundary leaks, anemic models, primitive obsession, weakened gates |

## How it's triggered

Superpowers has no extension API, so domain-powers attaches through Claude Code's own mechanisms:

| Mechanism | Strength | What it does |
|---|---|---|
| `SessionStart` hook | Soft | Injects `using-domain-powers` (the pairing table), like `using-superpowers` |
| Skill descriptions | Soft | Each skill's "Use when…" lets the model load it by itself; or call `/domain-powers:<skill>` |
| `PostToolUse` on `Skill` (`scripts/pair_skills.py`) | Deterministic prompt | When a `superpowers:*` skill loads, injects the paired domain-powers skills, and tells the coordinator to add a skill-loading line to implementer subagent prompts and to dispatch `domain-reviewer` |
| `PostToolUse` on Edit/Write (`scripts/domain_guard.py`) | Hard | Checks every edit, in the main session and in subagents |

The table above describes Claude Code. Codex uses `hooks/hooks-codex.json` through
`.codex-plugin/plugin.json`. Its startup hook also runs on resume and fork, and its
PostToolUse hook understands Codex's `apply_patch` payload. There is no automatic
Skill-event pairing hook in Codex; the startup instructions supply the pairing rules.

## Enforcement

A `PostToolUse` hook runs `scripts/domain_guard.py` after every Edit/Write to a source file (`.py`, `.pyi`, `.rs`) or a `.md` file and reports, **for the lines just written**. The guard core handles the hook payloads, scan mode and Markdown; each language pack (`scripts/languages/<language>.py`) supplies the source rules.

| Code | Python | Rust |
|---|---|---|
| `ANY` | `typing.Any` | `std::any::Any`, `dyn Any`, `downcast` |
| `CAST` | `typing.cast()` | `as` to a numeric type, `transmute` |
| `IGNORE` | `# type: ignore`, `# pyright: ignore`, `# mypy: ignore-errors` | `#[allow(..)]`, `#![allow(..)]`, `#[expect(..)]` |
| `UNTYPED` | functions missing annotations | |
| `UNSAFE` | | `unsafe` blocks, functions, impls, traits |
| `PANIC` | | `.unwrap()`, `.expect(..)`, `panic!`, `todo!`, `unimplemented!`, `unreachable!` |
| `DOMAIN-DEP` | domain importing frameworks/IO libs or non-domain modules | domain using framework/IO crates, `std::fs`/`net`/`process`/`env`, or non-domain modules |
| `LAYER` | application importing its own infrastructure | same |
| `CROSS-CTX` | importing another context's internals instead of its `api` | same |
| `TERM` | (Markdown) a word listed under **Avoid** in `docs/language.md` or `docs/domain/glossary.md`; code, inline code and URLs are skipped, and canonical terms are always allowed | same |

Outside domain layers, a deliberate exception is allowed with `domain-powers: allow <reason>` in a comment on the same line (`# ...` in Python, `// ...` in Rust, `<!-- ... -->` in Markdown), and the reviewer judges the reason. Inside domain layers, no exceptions are accepted. In test code only `IGNORE` is reported.

The same script runs over a whole tree for CI: `python3 scripts/domain_guard.py --scan src docs` (it skips `target/`, `.git/` and virtual environments).

## Project setup

Each language has a **pack card** in `skills/using-domain-powers/languages/<language>.md` with the full config and layout. In short:

**Python:** add to `pyproject.toml` (full template in `skills/quality-gates/languages/python/pyproject-template.toml`):

```toml
[tool.domain-powers]
root_package = "shop"
source_root = "src"
contexts = ["ordering", "billing"]
shared = ["shared_kernel"]
public_module = "api"
```

Layout per context: `<root>/<context>/{api.py, domain/, application/, infrastructure/}`.

**Rust:** add to the workspace `Cargo.toml` (full template, with `[workspace.lints]`, in `skills/quality-gates/languages/rust/Cargo-template.toml`; also `clippy-template.toml` and `deny-template.toml`):

```toml
[workspace.metadata.domain-powers]
contexts = ["ordering", "billing"]
shared = ["shared_kernel"]
public_module = "api"
```

Layout: one crate per context, `crates/<context>/src/{lib.rs, api.rs, domain/, application/, infrastructure/}`, with `lib.rs` exposing only `pub mod api` so the compiler enforces the context boundary. A core context can split its domain into `crates/<context>-domain` so Cargo enforces domain purity too.

Without the config table the guard still checks type escapes and treats anything under a `domain` directory or module as a domain layer.

Copy `skills/quality-gates/references/check.sh` to `scripts/check.sh` and vendor `scripts/domain_guard.py`, `scripts/languages/` and `scripts/assess/` as `scripts/domain-powers/`. The script runs the eight gates in order and picks the commands from `Cargo.toml` or `pyproject.toml`.

For the vocabulary check, copy `skills/defining-documentation-language/references/language-seed.md` to `docs/language.md` (the skill does this on first use) and edit it to match how your team talks.

## Assessing a migration

The `assessing-domain-migration` skill decides whether an existing codebase should move to a domain-driven layout, and keeps the move honest. Tools in `scripts/assess/` measure the code: an extractor per language (Python and Rust) writes a language-neutral model of units and dependencies, and `core.py analyse` scores it: layout style, cycles, hubs, instability, scattered terms, candidate clusters, escapes, framework references, and, given a `target.toml`, the distance from the agreed contexts. Anything a language cannot supply reads *n/a*, never zero.

The skill runs seven phases:

1. **Measure**: run the extractor and `analyse`.
2. **Read hotspots**: read only what the numbers point at.
3. **Language and contexts**: glossary and context map (checkpoint: your human partner agrees the contexts).
4. **Target**: write `target.toml` and re-run `analyse`.
5. **Decide**: migrate, migrate the core context only, or don't (checkpoint: your human partner decides).
6. **Plan**: split the work into slices, each its own plan.
7. **Baseline**: commit the assessment, `baseline.json` and `target.toml`.

From then on gate 8 (`migration`) runs `core.py compare` against `docs/domain/migration/baseline.json` and fails when any ratchet metric grew. The `domain-reviewer` agent has a migration mode that reports the same table and checks a change stays inside its slice.

## Language packs

The plugin is an agnostic core plus a **language pack** per language. The agnostic part (process, rules, data model, analysis, hook formats) never names a language's syntax or tools. A language pack is:

| Part | Where |
|---|---|
| Pack card: detection, config, guard codes, reviewer checklist | `skills/using-domain-powers/languages/<language>.md` |
| Skill variants: patterns, commands, templates | `skills/<skill>/languages/<language>.md` (and `languages/<language>/` for templates) |
| Guard module | `scripts/languages/<language>.py`, registered in `scripts/languages/__init__.py` |
| Assessment extractor | `scripts/assess/extractors/<language>.py`, which reuses the guard module's escape detection |

A variant declares what it supports, and the core treats anything undeclared as not applicable. Shipped packs: **Python** and **Rust**. Adding a language means adding these files, a row to the shipped tables (gate command map, extractor table) and a `case` in `check.sh`.

## Tested against

Two sample two-context projects (ordering, billing). `examples/sample-shop` (Python) passes every gate that applies to it (the migration gate needs a baseline; a scratch run showed it passing, then failing on an added import cycle) with ruff, mypy, import-linter 2.16, Hypothesis and pytest. `examples/rust-shop` (Rust workspace) passes every gate with rustfmt, clippy pedantic under `-D warnings`, cargo-deny 0.20 and proptest, and a scratch migration baseline; an injected `unwrap()` and domain-to-`api` use were caught by the guard and clippy, and an import of another context's `domain` was caught by the guard and the compiler. Injected violations were caught by both the hook and import-linter, and a drifting plan document produced `TERM` findings for `stage`, `chunk`, `sub-step`, `review pass`, `fix pass`, `wave` and a glossary synonym. The plugin's own docs pass its vocabulary check.

## License

MIT
