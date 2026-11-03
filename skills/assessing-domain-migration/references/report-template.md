# Report Template

`core.py analyse` writes `assessment.md` with the generated sections filled in and four human sections left as placeholders:

```
<!-- human: see references/report-template.md -->
```

Replace each placeholder; leave the generated sections untouched. Do not leave a placeholder in a committed report.

If an extractor lacked capabilities, state them in one line at the top of the report, above the summary.

## Recommendation

One of three, in bold, first:

- **Migrate**: the scorecard shows structural pain across dimensions and the work list is bounded.
- **Migrate the core context only**: the core context is where the value and the churn are; the rest stays as it is behind an anti-corruption layer.
- **Don't migrate**: the code is already adequate, or the cost clearly outweighs the benefit.

Then the reasons, each tied to a number from the report (scorecard dimension, work-list size, units to move, churn) or to a finding. Name what would change the recommendation. Note that the human partner decided, and when.

## Hotspot findings

One entry per finding, each with `file:line`:

- What is there (a hub, a cycle member, a scattered term, a model with framework refs).
- Why it matters for the migration.
- What it implies for the target or the slice order.

Cover hubs, cycle members, top scattered-term units, and model-like units with framework refs. A finding without a location is not a finding.

## Contexts

Link `docs/domain/glossary.md` and `docs/domain/context-map.md`. List each agreed context with its classification (core, supporting, generic), a one-line purpose, and how it maps to the candidate clusters (agreed as proposed, merged, split, or renamed, and why). If the clusters showed no separable seams, say so here.

## Slices

An ordered list. For each slice: its number, the contexts (or parts) it moves, the units, the incoming cross-context edges that drove its place in the order, and the plan that implements it once written. State the ordering rule used and any priority the human partner set.
