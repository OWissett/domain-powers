---
name: modeling-the-domain
description: Use when brainstorming or scoping a feature that involves business rules, entities with a lifecycle, money, scheduling, permissions, workflows, or any term the user uses that has a specific meaning in their business; also when code names disagree with how the user talks
---

# Modeling the Domain

## Overview

Runs *inside* `superpowers:brainstorming`. Brainstorming finds out what the person wants. This skill makes sure what they want is captured in their language, with its rules explicit and its boundaries drawn, before a plan exists.

**Core principle:** The model is the shared language. If the code uses a word the domain expert wouldn't recognise, or uses one word for two things, the model is wrong, however good the code is.

## The Iron Law

```
NO PLAN WITHOUT A GLOSSARY ENTRY FOR EVERY DOMAIN NOUN AND VERB IT USES
```

## Process

Do these as part of the brainstorming conversation, one question at a time, not as a questionnaire.

### 1. Harvest the language

While the person describes the feature, collect every noun and verb with business meaning. For each one, find out:
- What it means *to them* (one sentence, their words)
- What it is *not* (the nearby concept it gets confused with)
- Its lifecycle, if it has one: states and the events that move between them

Listen for **ambiguity signals**: the same word in two contexts with different rules ("order" in sales vs fulfilment), qualifiers ("pending order", "draft order") that are really separate states or types, and synonyms ("customer"/"client"/"account") that may or may not be the same thing. Ask which it is. Do not decide for them.

### 2. Storm the events (lightweight)

Ask: "Walk me through what happens, as a sequence of things that have *happened*." Write them as past-tense domain events (`OrderPlaced`, `PaymentCaptured`, `ShipmentDispatched`). For each event, find:
- The **command** that causes it, and who issues it
- The **rule** that can reject the command (this is an invariant; it is the most valuable thing you will find)
- The **data** that must be consistent at the moment the rule is checked (this is your aggregate boundary candidate)

See `references/event-storming-lite.md` for the format.

### 3. Find the seams

Group events and terms. Where a term changes meaning, where a different person or team owns the rules, or where consistency can be eventual rather than immediate, you have a **bounded context** boundary. For each pair of contexts that talk, name the relationship (see `references/context-mapping.md`). Most real systems need an **anti-corruption layer** wherever they touch a legacy system or third-party API.

Classify each context: **core** (the reason the business exists; invest in modelling), **supporting** (needed and specific, but not differentiating), or **generic** (buy it or use a library). Put strong typing and rich models in the core; keep generic contexts thin.

### 4. Write it down

Create or update, in the repo:
- `docs/domain/glossary.md`: one entry per term, grouped by context (template in `references/templates.md`)
- `docs/domain/context-map.md`: contexts, classification, relationships, and the integration style of each relationship
- Invariants go in the glossary entry of the concept that owns them, phrased as testable rules ("An Order's total never goes below zero", not "orders should be valid")

Read these back to the person and get explicit agreement on the terms before the brainstorming design is approved. A disagreement found here costs a sentence. Found in review, it costs a refactor.

## Existing codebases

Before inventing terms, grep the code for the concepts. If the code and the person disagree, surface it: "The code calls this `Account` but you've said *Customer* three times; are they the same thing?" Record the agreed term. If renaming is out of scope, record the mapping in the glossary under "Code aliases" so the next agent doesn't guess.

## Rationalizations

| Excuse | Reality |
|---|---|
| "The domain is obvious" | Then the glossary takes five minutes. Write it. |
| "We'll figure out boundaries when we hit them" | You'll hit them as a tangle of cross-imports. Draw them while it's cheap. |
| "One `User` model is simpler" | A user who pays, a user who ships, and a user who logs in have different rules. One model means every context's rules leak into every other. |
| "I'll ask about invariants during implementation" | Invariants decide aggregate boundaries, which decide the plan. Ask now. |
| "Event storming is a workshop thing" | The lite version is three questions. It surfaces the rules you'd otherwise miss. |

## Hand-off

The brainstorming design document should reference the glossary and context map, and list per context: its aggregates (candidates), its invariants, and the events it publishes or consumes. `domain-powers:designing-boundaries` picks this up during `superpowers:writing-plans`.
