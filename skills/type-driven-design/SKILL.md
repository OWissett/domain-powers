---
name: type-driven-design
description: Use when writing or changing domain or application code - especially when reaching for a string, integer, map or optional for a domain concept, adding validation checks, using a type escape (Any, cast, unsafe, unwrap, a suppression comment or attribute), writing boolean flags for state, or when type-checker or compiler errors tempt a suppression
---

# Type-Driven Design

## Overview

Pairs with `superpowers:test-driven-development`. Tests prove the cases you thought of. Types rule out cases nobody thought of. In the domain layer, aim for: **if it passes the strictest type check the project runs, the invalid state cannot be built.**

**Core principle:** Parse, don't validate. Turn untrusted input into a precise type once, at the edge. Inside the boundary, never check again, because the type already proves it.

## Language variants

Read the variant for the project's language before writing code: `languages/python.md` or `languages/rust.md` in this skill's directory. It has the code for every pattern below, which tools belong in which layer, and the exact suppression syntax.

## The Iron Law

```
NO TYPE ESCAPES IN DOMAIN OR APPLICATION CODE.
An escape is anything that tells the checker to take your word for it.
```

Each language has its own escapes (the variant lists them, and the guard reports them by code: `ANY`, `CAST`, `IGNORE`, plus `UNTYPED` for Python and `UNSAFE`, `PANIC` for Rust). The guard flags them the moment you write them. The only accepted form is a narrow, justified one with `domain-powers: allow <reason>` in a comment on the same line. Justified escapes belong in `infrastructure`, never `domain`.

## The patterns

Use them in this order of preference.

| Smell | Replace with |
|---|---|
| A primitive (`string`, `int`) for an ID, amount or email (primitive obsession) | **Value object** with a parsing constructor that validates, or a zero-cost **distinct identity type** when the concept has no rules beyond "is a different kind of X" |
| A status string or several boolean flags | **Enumeration** for flat states; **tagged union** (one variant per state) when states carry different data (`Draft \| Placed \| Cancelled`) |
| An optional field that is "required after step 2" | Separate types per lifecycle state (typestate). `PlacedOrder` *has* `placed_at`; `DraftOrder` doesn't have the field. |
| Absence checks scattered around | Parse once at the boundary into a non-optional type |
| An untyped map crossing a function boundary | A typed record at the edge, then parse into a domain type |
| Throwing or panicking for expected business failures | Return a **result type** (success or a union of outcomes), so callers *must* handle it. Reserve exceptions and panics for bugs and infrastructure faults. |
| `if/else` chains over a union or enum | Exhaustive matching, so adding a variant breaks the build in every place that must handle it |
| A mutable collection inside a value object | An immutable one (immutability is part of the value) |
| Entity fields set from outside | Methods named for domain verbs that enforce the invariant (`order.cancel(reason)`), with private state |

## Where each tool belongs

| Layer | Allowed |
|---|---|
| `domain` | The standard library's value, enum, identity and time types, and the shared kernel. **No serialization or validation frameworks**: their coercion ("1" becomes 1) and field-by-field construction are exactly the leniency the domain must not have. |
| `application` | Same as domain, plus ports. Commands and results are immutable values. |
| `infrastructure` / web | Serialization and validation frameworks, ORM types, for parsing *external* data, then immediately converting to domain types. |

The variant names the libraries for each layer.

## When the type checker complains

1. Read the error as a design review. "Expected `Sku`, found a string" means a raw string was about to reach the domain without being parsed. Parse it at the edge.
2. "Value may be absent" means you have an unproven assumption. Prove it with a narrowing check, or change the type so absence is impossible.
3. "Non-exhaustive match" or "missing return" means a variant isn't handled. Handle it.
4. A library has no types, or a weak API → wrap it in a typed adapter in `infrastructure`. Don't let the escape flow inward.

Only if all four fail, and only outside `domain`, use the narrowest escape the language allows, with a `domain-powers: allow <reason>` justification.

## Rationalizations

| Excuse | Reality |
|---|---|
| "A string is fine, it's just an ID" | Until an `OrderId` is passed where a `CustomerId` belongs. A distinct identity type costs one line. |
| "Strict mode is optional here" | Not here. Strict mode is the contract this codebase signed. |
| "This escape is safe, I know the type" | Then prove it with a narrowing check or a parse, and the checker will agree. An escape is the checker taking your word for it. |
| "The framework validates, so it's safe in the domain" | It coerces. Domain types must reject, not repair. |
| "Result types are unidiomatic here" | Unhandled business failures are worse. A union of outcomes plus an exhaustive match reads like plain code in every language. |
| "I'll fix the types after the tests pass" | TDD's red step includes *type* red. Write the types first; let the checker fail first. |
