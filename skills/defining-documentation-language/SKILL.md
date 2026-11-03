---
name: defining-documentation-language
description: Use when writing or editing any plan, spec, design doc, ADR, README, review, skill or other project documentation - especially when process words like `step`, `stage`, `phase`, `wave`, `round`, `batch`, `iteration` or `pass` are used loosely, when two documents name the same thing differently, or when docs/language.md does not exist yet
---

# Defining Documentation Language

## Overview

The domain glossary (`domain-powers:modeling-the-domain`) fixes the words for **the business**: Order, Refund, Customer. This skill fixes the words for **how the work is described**: phases, tasks, steps, rounds. Both drift the same way. One document says `wave`, the next says `round`, a third says `pass`, and an agent reading all three can't tell whether they are one thing or three.

**Core principle:** One concept, one term, everywhere. A synonym isn't a style choice. It's a claim that a second concept exists.

## The Iron Law

```
EVERY PROCESS OR STRUCTURE TERM IN A DOCUMENT IS DEFINED IN docs/language.md.
NO SYNONYMS. NO TERM USED FOR TWO THINGS.
```

## The two vocabularies

| File | Holds | Scope | Owner skill |
|---|---|---|---|
| `docs/language.md` | Process and structure terms: workflow, phase, plan, task, step, batch, round, fix wave, gate, checkpoint, finding; plus architecture terms (context, layer, port, adapter) | Whole project | This skill |
| `docs/domain/glossary.md` | Business terms and their rules | Per bounded context | `modeling-the-domain` |

Both use an **Avoid** list per term. The edit guard reads both and flags avoided words in any Markdown you write (`TERM` findings), outside code blocks and inline code.

## Process

### 1. No `docs/language.md` yet

Copy `references/language-seed.md` to `docs/language.md`. The seed matches superpowers' own usage, so plans and skills agree from day one. Then ask your human partner, one question at a time:
- "Your docs use *X* and *Y*. Are they the same thing?" (grep existing docs first; see step 3)
- Whether any seed term conflicts with how their team already talks. Their usage wins; update the seed row rather than fighting it.

### 2. Before writing any document

Read `docs/language.md`. When you need a word for a process concept:
- If a term exists, use it exactly (singular/plural is fine; synonyms are not).
- If none fits, **add the term first** (definition, what it is not, avoid list), then write the document. Never coin a term inline.
- If an existing term is *almost* right, don't stretch it. Ask whether this is a new concept.

### 3. Auditing existing docs

```bash
grep -rniwE "stage|wave|round|pass|iteration|cycle|batch|phase|step|chunk" docs/ README.md
```
Group the hits by the concept they mean, not the word used. Each concept gets one term; the others go in its Avoid list. Fix the documents in the same change, so the guard starts from zero findings.

### 4. When the guard flags a `TERM`

Replace the word with the canonical term. Words inside code blocks and `inline code` are never flagged, so quote a word when you are talking *about* it. If the use is legitimately different (e.g. "git stage", "context window"), add the exact phrase to **Allowed phrases** in `docs/language.md`. That is a vocabulary change, so mention it in your report so your human partner sees it. For a single line that must use the word (quoting an external source, say), end it with `<!-- domain-powers: allow <reason> -->`. Files that define vocabulary (they contain an **Avoid** list) are never checked.

## Writing rules

- **Hierarchy words are strict.** A plan contains tasks; a task contains steps. Never "step 3 of the plan" when it's a task, never "task 2.1" for a step.
- **Count with the term.** "Task 4, step 2", "round 3", not "the fourth one".
- **Name the scope of "context".** In this codebase *context* means bounded context. For the model's working memory write *context window*.
- **Same term in headings, prose and diagrams.** A diagram labelled `stages` in a doc that says `phases` is drift.
- **Superpowers terms are inherited.** Don't rename superpowers concepts in project docs. If the project needs a different word, record the mapping in `docs/language.md` under "Aliases".

## Rationalizations

| Excuse | Reality |
|---|---|
| "Varying the word reads better" | In docs agents act on, variation reads as a different instruction. Repeat the term. |
| "Everyone knows round and pass mean the same" | Then writing one of them costs nothing. The next agent doesn't know. |
| "It's just prose, not code" | Plans *are* the agent's code. A drifting term makes it execute the wrong loop. |
| "I'll add it to language.md later" | The guard flags it now, and the definition is cheapest while you still know what you meant. |
