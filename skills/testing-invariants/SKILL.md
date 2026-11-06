---
name: testing-invariants
description: Use when choosing which tests to write for domain code, value objects, aggregates, parsers, translators/ACLs, or a context's public api - or when tests only cover hand-picked examples, mock ports with a mocking library, or break whenever internals are refactored
---

# Testing Invariants

## Overview

Pairs with `superpowers:test-driven-development`, which still governs *how* (red, green, refactor; watch it fail). This skill governs *what*: in a domain model, the most valuable tests state rules that hold for **all** inputs, not outcomes for three examples.

**Core principle:** Every invariant in the glossary is a property test. Every boundary is a contract test. Every boundary rule is a tool-enforced architecture test.

## Language variants

Read the variant for the project's language: `languages/python.md` (Hypothesis) or `languages/rust.md` (proptest). It has the strategies, stateful tests, contract suites and CI settings.

## The Iron Law

```
EVERY INVARIANT WRITTEN IN docs/domain/glossary.md HAS A PROPERTY TEST THAT NAMES IT.
```

## The test portfolio, by layer

| Layer | Test kind | Speed |
|---|---|---|
| Value objects | Properties: construction rejects invalid input, operations preserve validity, algebraic laws (associativity of adding `Money`, `parse(format(x)) == x`) | ms |
| Aggregates | **Stateful** properties: any sequence of commands keeps every invariant true; examples for each expected-failure outcome | ms |
| Application | Use-case tests against **in-memory fakes** of ports (not mocks) | ms |
| ACL / translators | Example tests on **recorded real payloads**, plus "unknown enum value → explicit error" | ms |
| Adapters | Integration tests against real infrastructure; one shared **port contract suite** run against both the fake and the real adapter | s |
| Context `api` | Consumer-driven contract tests owned by the *consumer*, run in the *provider's* CI | ms |
| Architecture | Boundary contracts (gate 4 of `domain-powers:quality-gates`) plus the edit guard | ms |

## TDD loop with properties

1. **Red (types):** write the signature with precise types. Run the checker or compiler; it fails because the type or function doesn't exist.
2. **Red (property):** write the invariant as a property, named after the glossary line: `order_total_is_never_negative`. Watch it fail.
3. **Green:** implement until it passes. When the property tool shrinks a failure, keep its minimal example as a regression case (the variant says how).
4. **Refactor:** properties survive refactors that example tests break, which is the point.

## Strategy discipline

- Build generators **from the domain's own constructors**, so tests only generate valid values, and a separate generator produces *invalid* raw input to prove rejection.
- Register generators for value objects in one place, so every test gets valid domain values for free.
- Don't filter heavily (rejecting more than about half of the generated values): generate valid data constructively.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Three good examples cover it" | They cover what you imagined. Property tools find the empty list, the zero, the duplicate, the unicode SKU. |
| "Mocks are quicker than fakes" | A mock asserts calls you expected; a fake behaves like the port. The fake catches the bug where you call `add` twice. |
| "Stateful testing is overkill" | Aggregates *are* state machines. A 20-line machine tests thousands of command sequences. |
| "Architecture tests are slow / flaky" | Boundary contracts are static and run in seconds. |
| "The constructor enforces the invariant, so no test needed" | The test is what proves the constructor checks the right thing, and keeps checking after a refactor. |
