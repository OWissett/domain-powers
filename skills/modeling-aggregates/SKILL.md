---
name: modeling-aggregates
description: Use when implementing entities, business rules, state transitions, or domain events - or when business logic is in services/handlers/views instead of the model, entities are bags of public fields, a transaction updates several entities, or one object references another by holding it rather than its ID
---

# Modeling Aggregates

## Overview

An aggregate is the unit that keeps an invariant true. Everything that must be consistent *at the moment a rule is checked* lives inside it; everything else is referenced by ID and kept consistent eventually.

**Core principle:** Invariants are enforced in exactly one place: the aggregate root's methods. If a rule can be broken by any code path that doesn't go through the root, the model is wrong.

## Language variants

Read the variant for the project's language: `languages/python.md` or `languages/rust.md` in this skill's directory. It shows the root, events, repositories and policies in that language.

## The Iron Law

```
ONE AGGREGATE PER TRANSACTION. STATE CHANGES ONLY THROUGH ROOT METHODS NAMED IN THE UBIQUITOUS LANGUAGE.
```

## Rules

1. **Small aggregates.** Start with the root plus only what an invariant requires. "Order contains Customer" is almost always wrong. Order holds `customer_id: CustomerId`.
2. **Reference other aggregates by ID**, never by object. This is what lets each one load, save and lock independently.
3. **Root methods are domain verbs** from the glossary: `order.place()`, `order.cancel(reason)`, `account.withdraw(amount)`. No `set_status()`, no public mutable fields, no `update(fields)`.
4. **Each method checks its preconditions, changes state, and records a domain event.** Either everything happens, or nothing does and the caller gets an expected-failure outcome (see `domain-powers:type-driven-design` on result types).
5. **Invariants that span aggregates are eventually consistent.** Use a domain event and a handler (policy) that issues a command to the other aggregate. If the business says "these must never disagree, not even for a second", the two are one aggregate. Ask before merging.
6. **No I/O inside aggregates.** If a rule needs external data (e.g. "SKU is sellable"), the application layer fetches it and passes it in as a value, or passes a domain-service port into the method. The same goes for the clock and ID generation: pass the time and the new ID in.
7. **Construction is a domain operation too.** Use a named factory (`Order::place(...)`, `Order.place(...)`) that enforces creation invariants; don't expose a raw constructor that can build an invalid aggregate. Reconstitution from storage goes through a separate, clearly marked path used only by repositories.

## Anemic model check

Before finishing a task, look at the application handler you wrote. If it contains conditionals about business state, assigns aggregate fields, or computes totals, that logic belongs in the aggregate. Move it, then re-run the tests. They should still pass, and you should be able to delete some handler tests in favour of faster aggregate tests.

## Rationalizations

| Excuse | Reality |
|---|---|
| "It's simpler to update Order and Inventory in one transaction" | Until two checkouts contend on the same Inventory row. Ask whether the business needs it atomic, or just reliable. |
| "Public fields are idiomatic here" | They're also how an invariant gets broken by a line nobody reviewed. Use methods; expose read-only accessors. |
| "The service layer already validates" | Then the rule exists in a place the next caller can skip. Put it in the root. |
| "Events are overkill for this" | They're how other aggregates and contexts learn what happened without coupling to you. Record them even if nobody listens yet. |
| "Holding the Customer object avoids a lookup" | It also makes Order's consistency boundary include Customer. Hold the ID. |
