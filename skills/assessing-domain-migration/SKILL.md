---
name: assessing-domain-migration
description: Use when deciding whether an existing codebase should move to a domain-driven layout, planning that move, or reviewing a change made during one
---

# Assessing a Domain Migration

## Overview

Moving a codebase to a domain-driven layout is expensive, and most of the cost is hidden until someone counts. This skill counts first: tools measure the code, the agent reads only what the numbers point at, and the human partner decides.

**Core principle:** Measure first, then decide. Every claim in the report is reproducible from the tool output or cites `file:line`.

## The Iron Law

```
NO MIGRATION PLAN WITHOUT A MEASURED BASELINE AND A TARGET THE HUMAN PARTNER HAS AGREED.
NO BIG-BANG REWRITE.
```

## Phases

Seven phases, two checkpoints. Do not start a phase before the previous one has its output.

| Phase | What happens | Output |
|---|---|---|
| 1. Measure | Detect languages from file types and manifests; run each matching extractor; run `analyse` (with `--churn` in git). With no extractor for a language, read the code and state the reduced capabilities at the top of the report. | `model.json`, `assessment.json` and `assessment.md` |
| 2. Read hotspots | Read only what the numbers point at: hubs, cycle members, top scattered-term units, model-like units with framework refs. Each finding cites `file:line`. | Findings in the report |
| 3. Language and contexts | Run `domain-powers:modeling-the-domain`, starting from the candidate clusters and scattered terms. Write the glossary (with code aliases and avoided words) and the context map with classifications. **Checkpoint: the human partner agrees the contexts.** | `docs/domain/glossary.md`, `context-map.md` |
| 4. Target | Write `target.toml`; re-run `analyse --target`. | Distance and work list |
| 5. Decide | Weigh the scorecard and the cost (work-list size, units to move) against the benefit (core-context centrality and churn). Recommend *migrate*, *migrate the core context only* or *don't migrate*, with reasons. **Checkpoint: the human partner decides.** | Recommendation section |
| 6. Plan | If migrating, split the work into slices and hand each to `superpowers:writing-plans` as its own plan. | Slice list in the report |
| 7. Baseline | Commit the dated assessment, `baseline.json` and `target.toml`; enable the `migration` gate through `domain-powers:quality-gates`. | Committed baseline |

Hand-offs: phase 3 goes to `domain-powers:modeling-the-domain`, phase 6 to `superpowers:writing-plans`, phase 7 to `domain-powers:quality-gates`.

## Slices

A **slice** is one unit of migration work that moves one context, or part of one, behind its boundary and ends with every gate green. Order slices by fewest incoming cross-context edges first, unless the human partner prioritises the core context by churn. Each slice:

1. Creates the context skeleton and its boundary rules in warn mode, with current violations recorded as exceptions.
2. Moves units; the old import paths stay as re-export shims, recorded as exceptions.
3. Adds the `api` facade and, for legacy callers, anti-corruption layers.
4. Shrinks the exceptions to zero, removes the shims, and makes the rules strict.
5. Refreshes the baseline.

Details are in `references/migration-playbook.md`.

## Running the tools

Run everything from the project root. `<skill>` is this skill's base directory.

1. **Check for generated or vendored code first** (protobuf output, migrations, `vendor/`, bundled third-party sources). Pass each location as `--exclude GLOB`; otherwise it distorts every metric.
2. **Pick the extractor** from the Shipped extractors table in `<skill>/tools/EXTRACTORS.md`. Run the extractor's command from that table, adding `--exclude` globs and `--out model.json`.
3. **Analyse:**

   ```bash
   python3 <skill>/tools/core.py analyse model.json --out-dir docs/domain/migration [--target docs/domain/migration/target.toml] [--churn]
   ```

   This writes `assessment.json` and `assessment.md` in the output directory. The generated report has four human sections (Recommendation, Hotspot findings, Contexts, Slices), each holding a placeholder; fill them as `references/report-template.md` describes.
4. **Compare** a later state against the committed baseline (exit 0: nothing worse; 1: a ratchet metric increased; 2: usage or schema error):

   ```bash
   python3 <skill>/tools/core.py compare --baseline docs/domain/migration/baseline.json --current <dir>/assessment.json
   ```

5. **Phase 7:** rename `assessment.md` to `assessment-YYYY-MM-DD.md` and `assessment.json` to `baseline.json`, both in `docs/domain/migration/`, and commit them with `target.toml`.

The scorecard rubric is in `references/scorecard.md`; recognising the starting layout is in `references/layout-patterns.md`.

## When the tools can't help

| Situation | What to do |
|---|---|
| No extractor for a detected language | Read the code yourself for the same facts (units, dependencies, type names). List the missing capabilities at the top of the report; the scorecard dimensions that need them read *n/a*. Offer to add an extractor from the contract in `tools/EXTRACTORS.md`. |
| Files skipped by the extractor | The report shows the count. Open the list: if skipped files are central (a hub, a model package), fix the cause or exclude them knowingly, and say which in the report. |
| "No separable clusters found" | A finding in itself: the code has no seams to cut along. Take contexts from the glossary and the human partner's language instead, and expect a larger work list. |
| Not a git repo | Churn reads *n/a*; decide on the other evidence. |

## Red flags

| Thought | Reality |
|---|---|
| "The numbers look fine, skip reading hotspots" | Numbers say where to look, not what is there. Read the hubs and cycle members. |
| "We'll agree contexts as we go" | Without agreed contexts there is no target, so no distance and no ratchet. Stop at the checkpoint. |
| "One slice for everything" | That is a big-bang rewrite in a smaller coat. One context, or part of one, per slice. |
| "Refresh the baseline to make the gate pass" | The ratchet exists to fail. Refresh only as the last step of a slice, after the exceptions are gone. |
| "The scorecard says migrate, so plan it" | The human partner decides at the checkpoint, not the scorecard. |
| "Skip the glossary, the clusters have names" | Cluster names are guesses from type names. The language comes from the people who use it. |
