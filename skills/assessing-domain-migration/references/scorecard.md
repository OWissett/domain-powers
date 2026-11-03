# Scorecard

Five dimensions, each scored 0 to 5, or *n/a* when the extractor lacks a needed capability. The score is a prompt for the conversation at the decide checkpoint, not a verdict.

| Dimension | Measure | 5 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|---|
| Boundaries | With target: share of edges crossing contexts outside public units. Without: share of units in group-level cycles. | 0% | ≤ 5% | ≤ 15% | ≤ 30% | ≤ 50% | > 50% |
| Language | Share of distinct terms that are scattered | ≤ 5% | ≤ 10% | ≤ 20% | ≤ 30% | ≤ 45% | > 45% |
| Model richness | Share of data-only types in model-like units | ≤ 20% | ≤ 35% | ≤ 50% | ≤ 65% | ≤ 80% | > 80% |
| Framework isolation | Share of model-like units (with a target: units in non-generic contexts) with framework refs | 0% | ≤ 10% | ≤ 25% | ≤ 50% | ≤ 75% | > 75% |
| Type safety | Escapes per 1,000 lines | 0 | ≤ 1 | ≤ 3 | ≤ 6 | ≤ 10 | > 10 |

## What each dimension says

| Dimension | Measures | Needs | A low score means |
|---|---|---|---|
| Boundaries | How tangled the dependencies are, or how much crosses context borders through internals | `edges` (and a target for the stronger reading) | Contexts cannot be cut without breaking many callers; the work list will be long |
| Language | Whether one concept is named across many packages | `types` | The same business term lives in several places; the glossary work in phase 3 matters most |
| Model richness | Whether model-like units hold behaviour or only data | `types`, `data_only`, `layer_hints` | Rules live in services; moving them into the model is the core of the migration |
| Framework isolation | Whether domain code depends on frameworks or I/O libraries | `framework_refs` | The model cannot be tested or moved without the framework |
| Type safety | Escapes from the type system (`ANY`, `CAST`, `IGNORE`, `UNTYPED`, or language-specific kinds) | `escapes` | Type-level guarantees cannot be added before the escapes are removed |

## The Boundaries cap

Without a target, Boundaries is capped at 4: there is nothing yet to measure contexts against, so a perfect score would claim more than the data shows. The cap lifts when `analyse` runs with `--target`.

## How *n/a* reads

An extractor declares the capabilities it supports. A dimension whose capability is undeclared is *n/a*, never 0: absence of a measurement is not a bad measurement. Read an *n/a* as "unknown, check by hand", and say so in the report. The `not_applicable` list in `assessment.json` names every metric left out and why.
