---
name: testing-invariants
description: Use when choosing which tests to write for Python domain code, value objects, aggregates, parsers, translators/ACLs, or a context's public api - or when tests only cover hand-picked examples, mock ports with unittest.mock, or break whenever internals are refactored
---

# Testing Invariants

## Overview

Pairs with `superpowers:test-driven-development`, which still governs *how* (red, green, refactor; watch it fail). This skill governs *what*: in a domain model, the most valuable tests state rules that hold for **all** inputs, not outcomes for three examples.

**Core principle:** Every invariant in the glossary is a property test. Every boundary is a contract test. Every boundary rule is a tool-enforced architecture test.

## The Iron Law

```
EVERY INVARIANT WRITTEN IN docs/domain/glossary.md HAS A HYPOTHESIS TEST THAT NAMES IT.
```

## The test portfolio, by layer

| Layer | Test kind | Tooling | Speed |
|---|---|---|---|
| Value objects | Properties: construction rejects invalid, operations preserve validity, algebraic laws (associativity of `Money.__add__`, `parse(format(x)) == x`) | `hypothesis` | ms |
| Aggregates | **Stateful** properties: any sequence of commands keeps every invariant true; examples for each expected-failure outcome | `hypothesis.stateful.RuleBasedStateMachine` | ms |
| Application | Use-case tests against **in-memory fakes** of ports (not mocks) | pytest | ms |
| ACL / translators | Example tests on **recorded real payloads**, plus "unknown enum value → explicit error" | pytest + fixtures | ms |
| Adapters | Integration tests against real infra; one shared **port contract suite** run against both the fake and the real adapter | pytest + testcontainers | s |
| Context `api` | Consumer-driven contract tests owned by the *consumer*, run in the *provider's* CI | pytest | ms |
| Architecture | import-linter contracts (+ the edit guard) | `lint-imports` | ms |

Examples and Hypothesis strategies: `references/hypothesis-patterns.md`.

## TDD loop with properties

1. **Red (types):** write the signature with precise types. Run the checker; it fails because the type or function doesn't exist.
2. **Red (property):** write the invariant as a property, named after the glossary line: `test_order_total_is_never_negative`. Watch it fail.
3. **Green:** implement until it passes. When Hypothesis shrinks a failure, add its minimal example as an `@example(...)` so it stays a regression test.
4. **Refactor:** properties survive refactors that example tests break, which is the point.

## Strategy discipline

- Build strategies **from the domain's own constructors** (`st.builds(Sku.parse, ...)`), so tests only generate valid values, and a separate strategy generates *invalid* raw input to prove rejection.
- Register strategies for value objects in one `tests/strategies.py` (`st.register_type_strategy`) so every test gets valid domain values for free.
- Don't filter heavily (`.filter()` rejecting > ~50%): generate valid data constructively.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Three good examples cover it" | They cover what you imagined. Hypothesis finds the empty tuple, the zero, the duplicate, the unicode SKU. |
| "Mocks are quicker than fakes" | A mock asserts calls you expected; a fake behaves like the port. The fake catches the bug where you call `add` twice. |
| "Stateful testing is overkill" | Aggregates *are* state machines. A 20-line machine tests thousands of command sequences. |
| "Architecture tests are slow / flaky" | `lint-imports` is static and runs in under a second. |
| "The invariant is enforced in `__post_init__`, so no test needed" | The test is what proves `__post_init__` checks the right thing, and keeps checking after a refactor. |
