---
name: using-domain-powers
description: Use when starting any conversation in a Python codebase alongside superpowers - establishes which domain-powers skill applies in each superpowers phase
---

<SUBAGENT-STOP>
If you were dispatched as a subagent for a specific task, ignore this skill unless your task prompt names a domain-powers skill.
</SUBAGENT-STOP>

# Using Domain Powers

Domain-powers extends superpowers. It never replaces a superpowers skill. Superpowers decides *how you work* (brainstorm, plan, TDD, review, verify). Domain-powers decides *what good looks like* in the domain model, its boundaries and its types.

**Process skills come first.** Invoke the superpowers process skill, then the domain-powers skill that pairs with it.

In Codex, load paired skills from their files, run the shared guard, and adapt
domain review to available subagent tools using [the Codex instructions](references/codex.md).

## Pairing

| You are in... | Also invoke |
|---|---|
| `superpowers:brainstorming` for anything touching business rules, data that has a lifecycle, or a new feature area | `domain-powers:modeling-the-domain` |
| Writing or editing any plan, spec, design doc, ADR, README, review or skill | `domain-powers:defining-documentation-language` |
| `superpowers:writing-plans` | `domain-powers:designing-boundaries`, `domain-powers:defining-documentation-language` |
| `superpowers:test-driven-development` writing domain code | `domain-powers:type-driven-design`, `domain-powers:modeling-aggregates` |
| `superpowers:test-driven-development` choosing which tests to write | `domain-powers:testing-invariants` |
| `superpowers:verification-before-completion` | `domain-powers:quality-gates` |
| `superpowers:requesting-code-review` | also dispatch the `domain-powers:domain-reviewer` agent |
| Assessing a codebase for a DDD migration, or reviewing a migration change | `domain-powers:assessing-domain-migration` |
| A new or unguarded Python project | `domain-powers:quality-gates` (setup section) before writing domain code |

In Claude Code, a hook also reminds you of the pairing each time a superpowers
skill loads. In Codex, apply this table after loading the superpowers skill.

## Where the domain lives

- `docs/domain/glossary.md`: the ubiquitous language. Code names must match it.
- `docs/language.md`: the documentation language (phase, plan, task, step, batch, round, fix wave, gate). Docs must match it.
- `docs/domain/context-map.md`: bounded contexts and how they relate.
- `docs/domain/decisions/`: ADRs for boundary and modelling decisions.
- `[tool.domain-powers]` in `pyproject.toml`: tells the edit guard where the contexts are.

If these exist, read the glossary, the documentation language and the context map before naming anything.

## The edit guard

With the plugin's edit hooks installed and trusted, the guard checks Claude
Edit/Write calls and Codex native patches. In skills-only mode, run it manually.

For Markdown edits, the guard flags words that the documentation language or
glossary lists under **Avoid** (`TERM`). Use the canonical term.

For Python edits, the guard checks for type escapes (`Any`, `cast`, bare
`# type: ignore`), framework imports inside a domain layer, and imports that reach
into another context's internals. When it reports a violation, fix the design.
Do not suppress it. A suppression is legitimate only with an inline justification:
`# domain-powers: allow <reason>`. The reviewer will judge that reason.

## Red flags

| Thought | Reality |
|---|---|
| "It's just CRUD, no domain here" | Ask what invariants the data has. If there are none, say so explicitly in the plan; usually there are. |
| "I'll use `dict` for now and add types later" | Later never comes. Types are the design. |
| "The guard is being pedantic" | The guard is the only part of the boundary that can't be rationalised. Change the code. |
| "I'll name it what the framework calls it" | Name it what the glossary calls it. Add the term if it's missing. |
