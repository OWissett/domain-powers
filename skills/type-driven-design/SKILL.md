---
name: type-driven-design
description: Use when writing or changing Python domain or application code - especially when reaching for str/int/dict/Optional for a domain concept, adding validation checks, using Any, cast or type: ignore, writing boolean flags for state, or when mypy/pyright errors tempt a suppression
---

# Type-Driven Design (Python)

## Overview

Pairs with `superpowers:test-driven-development`. Tests prove the cases you thought of. Types rule out cases nobody thought of. In the domain layer, aim for: **if it type-checks under `--strict`, the invalid state cannot be built.**

**Core principle:** Parse, don't validate. Turn untrusted input into a precise type once, at the edge. Inside the boundary, never check again, because the type already proves it.

## The Iron Law

```
NO TYPE ESCAPES IN DOMAIN OR APPLICATION CODE.
Any, cast(), bare # type: ignore, and untyped defs are design bugs, not typing problems.
```

The edit guard flags these the moment you write them. The only accepted form is a narrow, justified one:
`# type: ignore[import-untyped]  # domain-powers: allow vendor lib ships no stubs`. Justified suppressions belong in `infrastructure`, never `domain`.

## The patterns

Use them in this order of preference. Python code for each is in `references/python-patterns.md`.

| Smell | Replace with |
|---|---|
| `order_id: str`, `amount: int`, `email: str` (primitive obsession) | **Value object** (frozen dataclass with a `parse`/`create` classmethod that validates) or `NewType` for pure identity with no rules |
| `status: str` / several `is_x: bool` flags | **Enum** for flat states; **union of frozen dataclasses** when states carry different data (`Draft \| Placed \| Cancelled`) |
| `Optional` field that is "required after step 2" | Separate types per lifecycle state (typestate). `PlacedOrder` *has* `placed_at`; `DraftOrder` doesn't have the field. |
| `if x is None: raise` scattered around | Parse once at the boundary into a non-optional type |
| `dict[str, Any]` crossing a function boundary | `TypedDict` at the edge, then parse into a dataclass |
| Raising for expected business failures | Return a **result union** (`Ok[T] \| Err[E]`, or a union of outcome dataclasses), so callers *must* handle it. Reserve exceptions for bugs and infrastructure faults. |
| `if/elif` over a union or enum | `match` with a final `case _: assert_never(x)`, so adding a variant breaks the build in every place that must handle it |
| `list` in a value object | `tuple` (immutability is part of the value) |
| Mutable entity attributes set from outside | Methods named for domain verbs that enforce the invariant (`order.cancel(reason)`), with private state |

## Where each tool belongs

| Layer | Allowed |
|---|---|
| `domain` | stdlib `dataclasses`, `enum`, `typing` (`NewType`, `Protocol`, `Literal`, `assert_never`, `Self`), `decimal`, `datetime`, `uuid`. **No pydantic**: its coercion ("1" → 1) is exactly the leniency the domain must not have. |
| `application` | Same as domain, plus ports. Commands and results are frozen dataclasses. |
| `infrastructure` / `web` | pydantic, TypedDict, ORM models, for parsing *external* data, then immediately converting to domain types. |

## When the type checker complains

1. Read the error as a design review. "Argument has incompatible type `str`; expected `Sku`" means a raw string was about to reach the domain without being parsed. Parse it at the edge.
2. "Item None of `X | None` has no attribute" means you have an unproven assumption. Prove it with a narrowing check, or change the type so `None` is impossible.
3. "Missing return statement" after a `match` means a variant isn't handled. Handle it.
4. Library has no types → write a minimal `.pyi` stub or wrap it in a typed adapter in `infrastructure`. Don't let `Any` from it flow inward.

Only if all four fail, and only outside `domain`, use a narrow `# type: ignore[code]` with a `# domain-powers: allow <reason>` justification.

## Rationalizations

| Excuse | Reality |
|---|---|
| "A `str` is fine, it's just an ID" | Until an `OrderId` is passed where a `CustomerId` belongs. NewType costs one line. |
| "Python is dynamic, types are optional" | Not here. Strict mode is the contract this codebase signed. |
| "`cast` is safe, I know the type" | Then prove it with `isinstance` or a parse, and the checker will agree. `cast` is the checker taking your word for it. |
| "pydantic validates, so it's safe in the domain" | It coerces. Domain types must reject, not repair. |
| "Result types are un-Pythonic" | Unhandled business failures are worse. A union of outcome dataclasses plus `match` reads like plain Python. |
| "I'll fix the types after the tests pass" | TDD's red step includes *type* red. Write the types first; let the checker fail first. |
