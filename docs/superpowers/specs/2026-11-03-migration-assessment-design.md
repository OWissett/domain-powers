# Migration Assessment Skill: Design

Date: 2026-11-03
Status: Approved
Plugin: domain-powers (v0.2.0 → v0.3.0)

## 1. Understanding

**What was asked:** a skill that assesses a migration from other layouts to a domain-driven layout, usable to decide, plan and review that migration.

**Decisions made in brainstorming:**

| Question | Decision |
|---|---|
| Purpose | Decide and plan: is migration worth it, which target contexts, which order. Later changes are checked against its baseline. |
| Target contexts | The tooling proposes candidates; the human decides, through `domain-powers:modeling-the-domain`. |
| Codebase size | Small to medium (under ~30k lines). The agent may read hotspot code directly; tooling says where to look. |
| Approach | Measurement tooling plus a guided skill (approach A). |
| Language scope | Language-agnostic core with per-language extractors. Python extractor now; the extractor contract makes Rust, C and others later additions. |

**Assumptions** (not stated by the human partner):
- Typical starting layouts are technical layering (`models/`, `services/`, `views/`, `utils/`) or framework apps.
- Every claim in an assessment report must be reproducible from the tooling output or cite `file:line`.

**Success criteria:**
1. From the report alone, a human partner can decide whether to migrate, and which contexts first.
2. Two runs of the tooling on the same code produce identical numbers.
3. Each migration change can be checked mechanically: the ratchet fails if it moves away from the target.
4. Adding a language needs only a new extractor; the core, report, scorecard and ratchet are unchanged.

## 2. Scope

**In scope:** the `assessing-domain-migration` skill, its agnostic core tool, the Python extractor, the extractor contract, a `migration` gate, a migration mode for `domain-reviewer`, and the vocabulary term *slice*.

**Out of scope (separate specs):**
- Restructuring the existing plugin to the language-pack convention (skills, guard, gates and reviewer become agnostic with language variants). This spec defines the convention; the next spec applies it to everything built so far.
- Rust, C or other extractors.
- Any automated refactoring or code moves. The tooling measures; agents move code through normal superpowers plans.

## 3. Language-pack convention

Plugin-wide pattern, first used here: **an agnostic core plus a variant per language.**

- The agnostic part (process, rules, data model, analysis) never names a language's syntax or tools.
- Each language variant lives under a `languages/` (documents) or `extractors/` (tools) directory, named by language: `python`, `rust`, `c`.
- A variant declares what it supports. The core treats anything undeclared as *not applicable*, never as zero.
- The first variant shipped is Python.

## 4. Architecture

```
skills/assessing-domain-migration/
  SKILL.md                     agnostic process (section 8)
  references/
    scorecard.md               rubric with thresholds (section 6.4)
    layout-patterns.md         recognising starting layouts and mapping them to contexts
    migration-playbook.md      slices, warn-then-strict boundaries, facades, ACLs
    report-template.md         human-written sections of the report
  tools/
    core.py                    agnostic: analyse, compare
    EXTRACTORS.md              contract for new extractors (section 5)
    extractors/
      python.py                Python extractor (stdlib ast)
```

Flow:

```
extractor  ──>  model.json  ──>  core.py analyse [--target target.toml] [--churn]
                                     ├─> assessment.json
                                     └─> assessment.md
assessment.json + baseline.json ──> core.py compare ──> exit 0 / 1
```

Extractors are separate commands that write JSON, so an extractor may be written in any language. `core.py` never parses source code. Both tools are Python 3.11+ standard library only.

## 5. Neutral model and extractor contract

### 5.1 Model schema (`domain-powers.assess.model/1`)

```json
{
  "schema": "domain-powers.assess.model/1",
  "language": "python",
  "root": "src",
  "capabilities": ["edges", "types", "data_only", "escapes", "framework_refs", "layer_hints"],
  "units": [
    {
      "id": "shop.models.order",
      "path": "src/shop/models/order.py",
      "group": "shop.models",
      "loc": 120,
      "layer_hint": "models",
      "types": [{"name": "Order", "data_only": true}],
      "escapes": {"ANY": 2, "IGNORE": 1},
      "framework_refs": ["sqlalchemy"]
    }
  ],
  "edges": [{"from": "shop.services.billing", "to": "shop.models.order", "count": 3}],
  "skipped": [{"path": "src/shop/broken.py", "reason": "syntax error"}]
}
```

| Field | Meaning | Capability |
|---|---|---|
| `units[].id` | Stable logical name (Python module path, Rust crate::module, C file path) | always |
| `units[].group` | Package-level grouping used for package metrics | always |
| `units[].loc` | Non-blank, non-comment lines | always |
| `units[].layer_hint` | One of the hint vocabulary (5.2), or `null` | `layer_hints` |
| `units[].types` | Declared type names | `types` |
| `types[].data_only` | No behaviour beyond construction, accessors and dunder/derived methods | `data_only` |
| `units[].escapes` | Counts by kind (`ANY`, `CAST`, `IGNORE`, `UNTYPED`, or language-specific kinds) | `escapes` |
| `units[].framework_refs` | Framework or I/O libraries the unit uses | `framework_refs` |
| `edges` | Internal dependencies only (both ends are units) | `edges` |
| `skipped` | Files the extractor could not read, with reason | always |

### 5.2 Layer-hint vocabulary

`models`, `entities`, `schemas`, `services`, `managers`, `handlers`, `views`, `controllers`, `routes`, `api`, `repositories`, `dao`, `serializers`, `forms`, `tasks`, `utils`, `helpers`, `common`, `core`, `domain`, `application`, `infrastructure`, `adapters`, `tests`. Extractors map directory or file names onto this list (`repos` → `repositories`) and emit `null` otherwise.

Hints are grouped as **model-like** (`models`, `entities`, `schemas`, `domain`), **service-like** (`services`, `managers`, `handlers`, `application`), **edge** (`views`, `controllers`, `routes`, `api`, `serializers`, `forms`, `adapters`, `infrastructure`, `repositories`, `dao`, `tasks`) and **shared** (`utils`, `helpers`, `common`, `core`).

### 5.3 Extractor command line

```
<extractor> <source_root> --out model.json [--package NAME] [--include-tests] [--exclude GLOB ...]
```

- Exit 0 on success, even with skipped files; exit 2 on usage errors or an unreadable root.
- Tests are excluded by default (`layer_hint: tests` units are dropped unless `--include-tests`).
- Output is deterministic: units sorted by `id`, edges by `(from, to)`.

### 5.4 Python extractor

- Units are modules; `group` is the package one level below the root package (`shop.models`), or the root package for top-level modules.
- Edges come from `import` and `from … import`, with relative imports resolved; `from pkg import name` counts as an edge to `pkg.name` if that unit exists, otherwise to `pkg`.
- `data_only`: a class whose body has only annotations, assignments, docstrings, `@property`, `@dataclass` decoration, or dunder methods.
- Escapes: `ANY`, `CAST`, `IGNORE`, `UNTYPED`, with the same detection rules as the domain-powers edit guard. The logic is duplicated for now so the skill stays self-contained; the language-pack restructure spec merges the two.
- Framework refs: top-level imports matching the guard's domain-forbidden list.

## 6. Analysis (`core.py analyse`)

All metrics are computed from the model; each lists the capabilities it needs.

### 6.1 Shape

1. **Layout style:** by share of units per hint group. ≥ 50% of units with technical hints (`models`, `services`, `views`, `utils`…) gives *technical layering*; groups that each contain model-like, service-like and edge units give *framework apps / feature packages*; anything else gives *mixed*. Needs `layer_hints`.
2. **Cycles:** strongly connected components of size > 1, at unit level and at group level (Tarjan). Needs `edges`.
3. **Hubs:** the top 10 units by fan-in; per group, instability `I = Ce / (Ca + Ce)`. Needs `edges`.
4. **Churn** (optional, `--churn`): lines changed per unit over the last 12 months from `git log --numstat`. Language-agnostic; *not applicable* outside git.

### 6.2 Domain signals

5. **Term spread:** type names split on case and underscores into lower-case words of length ≥ 3, minus a stop list of technical words (`manager`, `service`, `helper`, `util`, `base`, `mixin`, `model`, `view`, `serializer`, `schema`, `dto`, `data`, `info`, `handler`, `controller`, `repository`, `factory`, `impl`, `abstract`, `config`, `test`). A term in ≥ 3 groups is *scattered*. Needs `types`.
6. **Model richness:** share of `data_only` types in model-like units, and the count of types in service-like units. Needs `types`, `data_only`, `layer_hints`.
7. **Framework entanglement:** share of model-like units (or, with a target, units assigned to any context whose classification is not `generic`) with framework refs. Needs `framework_refs`.
8. **Type escapes:** total and per 1,000 lines, by kind. Needs `escapes`.

### 6.3 Candidate contexts

9. Deterministic weighted label propagation over units:
   - Weight `w(u, v) = deps(u→v) + deps(v→u) + 2 × jaccard(terms(u), terms(v))`; term pairs are counted only where the units share at least one term.
   - Every unit starts with its own label. Iterate units sorted by `id`; each takes the label with the highest summed weight among its neighbours, ties broken by the lexicographically smallest label. Stop when nothing changes, or after 50 sweeps over all units.
   - Singleton clusters merge into the neighbouring cluster with the highest weight; isolated units are reported as *unclustered*.
   - Each cluster is named by its top three terms by `tf × log(clusters / clusters containing term)`, with members and cohesion (`internal edges / all edges touching the cluster`).

   Without `edges`, clustering uses terms only; without `types`, edges only; with neither, *not applicable*.

### 6.4 Scorecard (0–5 each, or n/a)

| Dimension | Measure | 5 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|---|
| Boundaries | With target: share of edges crossing contexts outside public units. Without: share of units in group-level cycles. | 0% | ≤ 5% | ≤ 15% | ≤ 30% | ≤ 50% | > 50% |
| Language | Share of distinct terms that are scattered | ≤ 5% | ≤ 10% | ≤ 20% | ≤ 30% | ≤ 45% | > 45% |
| Model richness | Share of data-only types in model-like units | ≤ 20% | ≤ 35% | ≤ 50% | ≤ 65% | ≤ 80% | > 80% |
| Framework isolation | Metric 7 | 0% | ≤ 10% | ≤ 25% | ≤ 50% | ≤ 75% | > 75% |
| Type safety | Escapes per 1,000 lines | 0 | ≤ 1 | ≤ 3 | ≤ 6 | ≤ 10 | > 10 |

Without a target, Boundaries is capped at 4: there is nothing yet to measure contexts against.

### 6.5 Distance to target

`--target docs/domain/migration/target.toml`:

```toml
[contexts.ordering]
classification = "core"            # core | supporting | generic
units = ["shop.models.order*", "shop.services.checkout*"]
public = ["shop.services.checkout"]

[contexts.billing]
classification = "supporting"
units = ["shop.services.billing*", "shop.models.invoice*"]
public = ["shop.services.billing.api"]
```

Patterns are `fnmatch` globs on unit `id`; a unit matching several contexts is an error (exit 2, listing the overlaps). Outputs:
- **unassigned units**: matching no context
- **cross-context edges** by context pair, split into *via public units* and *into internals*
- **context cycles**: strongly connected components in the context graph
- **work list**: every edge into internals, sorted by context pair, then count

### 6.6 Outputs

- `assessment.json`: schema `domain-powers.assess.result/1`, every metric above, plus `capabilities` and `not_applicable` lists. This is the baseline format.
- `assessment.md`: generated sections (summary table, scorecard, layout, cycles, hubs, scattered terms, candidate contexts, distance, work list), with clearly marked placeholders for the human-written sections in `report-template.md`.

## 7. Ratchet (`core.py compare`)

```
core.py compare --baseline baseline.json --current assessment.json
```

Ratchet metrics, which must not increase: unit-level cycle members, cross-context edges into internals, total escapes, framework refs in non-generic context units, and unassigned units. Cross-context edges into internals, framework refs and unassigned units need a target in both files; if the targets differ, `compare` reports that and checks only the target-independent metrics. Exit 0 if none increased, 1 if any did (printing a delta table), 2 for schema or usage errors. Decreases are reported as progress.

## 8. Skill process

The skill runs in seven phases, with two checkpoints.

| Phase | What happens | Output |
|---|---|---|
| 1. Measure | Detect languages from file types and manifests; run each matching extractor; run `analyse` (with `--churn` in git). With no extractor for a language, the agent reads the code and states the reduced capabilities at the top of the report. | `model.json`, `assessment.json/.md` |
| 2. Read hotspots | Read only what the numbers point at: hubs, cycle members, top scattered-term units, model-like units with framework refs. Each finding cites `file:line`. | Findings in the report |
| 3. Language and contexts | Run `modeling-the-domain` starting from candidate clusters and scattered terms; write the glossary (with code aliases and avoided words) and the context map with classifications. **Checkpoint:** the human partner agrees the contexts. | `docs/domain/glossary.md`, `context-map.md` |
| 4. Target | Write `target.toml`; re-run `analyse --target`. | Distance and work list |
| 5. Decide | Weigh scorecard and cost (work-list size, units to move) against benefit (core-context centrality and churn). Recommend *migrate*, *migrate the core context only* or *don't migrate*, with reasons. **Checkpoint:** the human partner decides. | Recommendation section |
| 6. Plan | If migrating, split into slices (see 8.1), each handed to `superpowers:writing-plans` as its own plan. | Slice list in the report |
| 7. Baseline | Commit `docs/domain/migration/assessment-YYYY-MM-DD.md`, `baseline.json` and `target.toml`; enable the `migration` gate. | Committed baseline |

**Iron law:** no migration plan without a measured baseline and a target the human partner has agreed, and no big-bang rewrite.

### 8.1 Slices

A **slice** is one unit of migration work that moves one context, or part of one, behind its boundary and ends with every gate green. Ordering: fewest incoming cross-context edges first, unless the human partner prioritises the core context by churn. Each slice:

1. Creates the context skeleton and its boundary rules in warn mode, with current violations recorded as exceptions.
2. Moves units; the old import paths stay as re-export shims, recorded as exceptions.
3. Adds the `api` facade and, for legacy callers, anti-corruption layers.
4. Shrinks the exceptions to zero, removes the shims, and makes the rules strict.
5. Refreshes the baseline.

## 9. Integration with the plugin

- **Vocabulary:** add *slice* to the language seed, with avoided words `migration step`, `increment`, `migration phase`.
- **quality-gates:** gate 8, `migration`, runs `compare` when `docs/domain/migration/baseline.json` exists; `check.sh` gains the matching line.
- **domain-reviewer:** a migration mode. Given baseline and current assessments, it reports the delta table as tool evidence and checks the change belongs to the current slice, shrinks rather than adds exceptions, and adds no new shims.
- **using-domain-powers:** a routing row: "assessing a codebase for a DDD migration, or reviewing a migration change → `domain-powers:assessing-domain-migration`".
- **README:** a section on assessment, plus the language-pack convention.
- **Packaging:** `docs/` is excluded from the `.plugin` archive.

## 10. Errors and edge cases

| Situation | Behaviour |
|---|---|
| A file fails to parse | Listed in `skipped`; the report shows the count; analysis continues |
| No extractor for a detected language | Phase 1 falls back to the agent reading the code; the report header lists the missing capabilities |
| Not a git repo, or `git` unavailable | Churn is *not applicable* |
| One group, or no internal edges | Group-level metrics are *not applicable*; clustering uses terms only |
| Every unit ends up in one cluster | Reported as "no separable clusters found", a finding in itself |
| Target pattern overlaps | Exit 2, listing the overlapping units and contexts |
| Baseline from a different schema version | Exit 2 with both versions named |
| Generated or vendored code | Excluded with `--exclude`; the skill tells the agent to check for these before measuring |
| Namespace packages (no `__init__.py`) | Treated as packages if they contain `.py` files |

## 11. Testing

- **Core unit tests** (pytest, hand-built models): cycle detection, hub ranking, instability, term splitting and stop words, scattered terms, deterministic clustering (same input, same labels across runs and with shuffled input order), scorecard thresholds at every boundary, target matching and overlap errors, every `compare` outcome (worse → 1, equal or better → 0, mismatched schema → 2, differing targets → target-independent checks only), and *not applicable* handling for each missing capability.
- **Python extractor tests:** a fixture package covering relative imports, `from pkg import module`, dataclasses vs behaviour classes, each escape kind, framework imports, tests excluded by default, syntax-error files skipped.
- **End-to-end:** a legacy-layout fixture (`models/`, `services/`, `views/`, `utils/` with a cycle, a hub `models` module, scattered `Order`/`Invoice` terms, and framework imports in models), asserting layout style, the cycle, the hub, the scattered terms, two candidate clusters matching ordering and billing, and distance numbers for a given target. Then a simulated slice that moves the billing modules must make `compare` pass, and a change adding a cross-context import must make it fail.
- **Quality bar:** both tools pass ruff with the plugin template and `mypy --strict`; the skill's Markdown passes the plugin's own vocabulary check; `claude plugin validate` passes.
