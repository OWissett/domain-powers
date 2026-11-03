---
name: designing-boundaries
description: Use when writing an implementation plan, adding a module or package, integrating an external API or legacy system, or when one part of a Python codebase starts importing another's internals, ORM models leak into business logic, or circular imports appear
---

# Designing Boundaries

## Overview

Runs *inside* `superpowers:writing-plans`. The plan already says which files and which tests. This skill makes it also say **which context, which layer, and which invariants**, and makes the boundaries mechanically checkable before the first line of code.

**Core principle:** A boundary that isn't enforced by a tool is a suggestion. Agents (and people) under time pressure ignore suggestions.

## The Iron Law

```
DEPENDENCIES POINT INWARD. DOMAIN IMPORTS NOTHING BUT THE STANDARD LIBRARY AND THE SHARED KERNEL.
```

## The shape

Per bounded context (full layout and contracts in `references/python-layout.md`):

```
src/<app>/<context>/
  api.py            # the ONLY module other contexts may import
  domain/           # entities, value objects, aggregates, domain events, repository Protocols
  application/      # use cases / command handlers; orchestrate domain + ports
  infrastructure/   # adapters: ORM repositories, HTTP clients, ACL translators
```

Rules:
1. `domain` → stdlib, `<app>.shared_kernel`. Nothing else: no ORM, no web framework, no pydantic, no `requests`, no `os.environ`.
2. `application` → `domain`. It depends on **ports** (`typing.Protocol` defined in `domain` or `application`), never on adapters.
3. `infrastructure` → `application`, `domain`, third-party libraries.
4. Other contexts → `<context>.api` only. `api` exposes commands, DTOs, query functions and integration events, **never domain objects**.
5. Wiring happens in one composition root (`<app>/bootstrap.py`), the only place that knows concrete adapters.

## Ports and adapters

Define what the domain *needs* in the domain's language, then adapt the world to it. See `references/ports-and-adapters.md` for Python patterns: repository Protocols, unit of work, ACL translators, and in-memory fakes for tests.

## What the plan must contain

Add these to the `superpowers:writing-plans` output.

**Plan header**, after the Architecture line:
```markdown
**Contexts touched:** Ordering (core), Billing (supporting)
**Glossary:** docs/domain/glossary.md (terms added: Refund, RefundPolicy)
**New boundaries:** billing.infrastructure.acl.stripe (ACL for Stripe)
**Boundary contracts:** pyproject.toml [tool.importlinter] (contracts added: billing-domain-pure)
```

**Per task**, in the Files block:
```markdown
**Context / layer:** Billing / domain
**Aggregate:** Refund
**Invariants protected:** Refund amount ≤ captured amount; one Refund per Payment at a time
**Ports:** RefundRepository (new Protocol), PaymentGateway (existing)
```

**Ordering of tasks:** inside-out. Domain types and invariant tests first (pure, fast, no fakes needed), then application use cases against in-memory fakes, then infrastructure adapters with integration tests, then wiring. A task that writes an adapter before the port it implements exists is out of order.

**First task in a new context:** create the package skeleton *and* add its import-linter contracts *and* register it in `[tool.domain-powers]`. The boundary exists before the code that might violate it.

## Integrating with the outside

Every external system (payment provider, legacy DB, partner API, even your own other service) gets an anti-corruption layer in `infrastructure/acl/<system>.py`: a translator that maps their types to yours, plus an adapter that implements your port. Their field names, enums, and error types stop at the ACL. Test the translator with recorded real payloads.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Importing the ORM model in the domain saves a mapping layer" | It welds your invariants to your schema. Every migration becomes a domain change. Map. |
| "Other contexts can just import our domain classes, it's one codebase" | Then you have one context, with extra folders. Expose DTOs via `api.py`. |
| "Protocols are ceremony for one implementation" | You have two: the real adapter and the in-memory fake your tests use. |
| "We'll add the import-linter contract after it works" | After it works there'll be three violations to argue about. Add it first. |
| "This helper is needed in both contexts, put it in shared_kernel" | Shared kernel is for stable value types. Behaviour that might diverge gets duplicated. |
