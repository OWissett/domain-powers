# domain-powers

Domain-driven design, strong boundaries and type-level guarantees for Python coding agents. Built as a companion to [superpowers](https://github.com/obra/superpowers): superpowers sets *how* the agent works (brainstorm → plan → TDD → review → verify), and domain-powers sets *what good looks like* in the model, its boundaries and its types.

**Requires:** the superpowers plugin, Python ≥ 3.11 on the machine running hooks (for `tomllib`). Target projects use Python ≥ 3.12.

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
| `test-driven-development` | **type-driven-design**: value objects, NewType IDs, typestate unions, result unions, `assert_never`, parse-don't-validate |
| | **modeling-aggregates**: small aggregates, root-only mutation, domain events, ID references, idempotent policies |
| | **testing-invariants**: Hypothesis properties and stateful machines per glossary invariant; fakes over mocks; port contract suites |
| `verification-before-completion` | **quality-gates**: eight gates (ruff format, ruff lint, mypy strict, import-linter, escape scan, pytest+Hypothesis, documentation language, migration) and brownfield ratchets |
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

A `PostToolUse` hook runs `scripts/domain_guard.py` after every Edit/Write to a `.py` or `.md` file and reports, **for the lines just written**:

| Code | Catches |
|---|---|
| `ANY` | `typing.Any` |
| `CAST` | `typing.cast()` |
| `IGNORE` | `# type: ignore`, `# pyright: ignore`, `# mypy: ignore-errors` |
| `UNTYPED` | functions missing annotations |
| `DOMAIN-DEP` | domain importing frameworks/IO libs or non-domain modules |
| `LAYER` | application importing its own infrastructure |
| `CROSS-CTX` | importing another context's internals instead of its `api` |
| `TERM` | (Markdown) a word listed under **Avoid** in `docs/language.md` or `docs/domain/glossary.md`; code, inline code and URLs are skipped, and canonical terms are always allowed |

Outside domain layers, a deliberate exception is allowed with `# domain-powers: allow <reason>` on the same line (`<!-- domain-powers: allow <reason> -->` in Markdown), and the reviewer judges the reason. Inside domain layers, no exceptions are accepted.

The same script runs over a whole tree for CI: `python3 scripts/domain_guard.py --scan src docs`.

## Project setup

Add to your `pyproject.toml` (full template in `skills/quality-gates/references/pyproject-template.toml`):

```toml
[tool.domain-powers]
root_package = "shop"
source_root = "src"
contexts = ["ordering", "billing"]
shared = ["shared_kernel"]
public_module = "api"
```

Without this table the guard still checks type escapes and treats any `*/domain/*.py` as a domain layer.

Expected layout per context: `<root>/<context>/{api.py, domain/, application/, infrastructure/}`.

For the vocabulary check, copy `skills/defining-documentation-language/references/language-seed.md` to `docs/language.md` (the skill does this on first use) and edit it to match how your team talks.

## Assessing a migration

The `assessing-domain-migration` skill decides whether an existing codebase should move to a domain-driven layout, and keeps the move honest. Tools in `skills/assessing-domain-migration/tools/` measure the code: an extractor (Python today) writes a language-neutral model of units and dependencies, and `core.py analyse` scores it: layout style, cycles, hubs, instability, scattered terms, candidate clusters, escapes, framework references, and, given a `target.toml`, the distance from the agreed contexts. Anything a language cannot supply reads *n/a*, never zero.

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

A plugin-wide convention, used first by the assessment tools: an agnostic core plus a variant per language. The agnostic part (process, rules, data model, analysis) never names a language's syntax or tools. Each variant lives under a `languages/` (documents) or `extractors/` (tools) directory, named by language. A variant declares what it supports, and the core treats anything undeclared as not applicable. Python is the first variant shipped.

## Tested against

A sample two-context project (ordering, billing) passing every gate that applies to it (the migration gate needs a baseline; a scratch run showed it passing, then failing on an added import cycle) with ruff 0.16, mypy 2.3, import-linter 2.x, Hypothesis and pytest. Injected violations were caught by both the hook and import-linter, and a drifting plan document produced `TERM` findings for `stage`, `chunk`, `sub-step`, `review pass`, `fix pass`, `wave` and a glossary synonym. The plugin's own docs pass its vocabulary check.

## License

MIT
