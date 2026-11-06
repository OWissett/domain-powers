# Documentation Language

One concept, one term. This file defines the words used in this project's plans, specs, reviews, ADRs and skills. Business terms live in `docs/domain/glossary.md`.

The domain-powers edit guard reads the **Avoid** column and flags those words in Markdown (outside code). Comma-separate entries; multi-word phrases are allowed.

## Terms

### Work structure

| Term | Definition | Not | Avoid |
|---|---|---|---|
| workflow | The full superpowers sequence for a piece of work: brainstorming → planning → implementation → review → verification → finishing | A single plan | process flow |
| phase | One named part of the workflow (brainstorming phase, planning phase) or of a process skill (debugging Phase 1–4; RED, GREEN, REFACTOR) | A unit of planned work | stage |
| plan | The implementation document in `docs/superpowers/plans/`, made of tasks | A spec or design doc | roadmap, work plan |
| task | The smallest plan unit that carries its own test cycle and gets its own review | A step | work item, subtask, chunk, ticket |
| step | One action inside a task with a checkable result ("run the test, see it fail") | A task | substep, sub-step, action item |
| batch | Several small, same-shape tasks sent to one subagent together and reviewed as one diff | A wave or a round | task group, wave |
| round | One review → fix iteration on a single task or batch, counted from 1 | The final fix wave | fix cycle, review cycle, review pass, iteration |
| fix wave | The single set of fixes after the final whole-branch review; there is only ever one | A round | fix pass, final pass |
| slice | One unit of migration work that moves one context, or part of one, behind its boundary and ends with every gate green | A plan (each slice gets its own plan) | migration step, increment, migration phase |
| checkpoint | A point where work stops for your human partner's decision | A gate | milestone, sign-off point |

### Quality

| Term | Definition | Not | Avoid |
|---|---|---|---|
| gate | One automated check in `scripts/check.sh` that must exit 0 | A review or a checkpoint | quality check, guardrail |
| guard | The domain-powers hook that checks each edit as it is written | A gate | linter hook, watcher |
| finding | One issue a review or the guard reports, with a severity | A gate failure | remark |
| severity | Critical, Important or Minor, as defined by superpowers review | Priority | blocker, nit |
| invariant | A business rule that must always hold, stated in the domain glossary | A test | business invariant |

### Architecture

| Term | Definition | Not | Avoid |
|---|---|---|---|
| context | A bounded context: a package, module or crate where each domain term has one meaning | The model's working memory (say "context window") | domain area, subdomain |
| layer | One of domain, application, infrastructure, plus the `api` module, inside a context | A context | architectural tier |
| port | A contract the domain or application declares for something it needs (a Python `Protocol`, a Rust trait) | Its implementation | interface, abstraction |
| adapter | An infrastructure type implementing a port | A port | driver |
| domain event | A past-tense fact recorded by an aggregate, internal to its context | An integration event | domain message |
| language pack | The per-language files for one language: pack card, skill variants, guard module and extractor | The agnostic core they plug into | language plugin, language support module |
| integration event | A versioned event in a context's public `api` module, for other contexts | A domain event | external event, public event |

## Allowed phrases

Exact phrases the guard ignores even though they contain an avoided word. Canonical terms (the Term column) are always allowed, so `fix wave` is fine even though `wave` alone is avoided.

- `git stage`
- `stage files`
- `staging environment`
- `context window`
- `user interface`

## Aliases

Terms from other tools or teams, mapped to ours. Use ours in writing.

| Their term | Our term | Where it comes from |
|---|---|---|
| fix pass | fix wave | superpowers executing-plans skill |
