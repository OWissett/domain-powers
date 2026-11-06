---
name: designing-boundaries
description: Use when writing an implementation plan, adding a module, package or crate, integrating an external API or legacy system, or when one part of a codebase starts reaching into another's internals, ORM or framework types leak into business logic, or circular dependencies appear
---

# Designing Boundaries

## Overview

Runs *inside* `superpowers:writing-plans`. The plan already says which files and which tests. This skill makes it also say **which context, which layer, and which invariants**, and makes the boundaries mechanically checkable before the first line of code.

**Core principle:** A boundary that isn't enforced by a tool is a suggestion. Agents (and people) under time pressure ignore suggestions.

## Language variants

Read the variant for the project's language: `languages/python.md` (package layout, import-linter contracts, ports as Protocols) or `languages/rust.md` (workspace layout, visibility, cargo-deny bans, ports as traits). It has the full layout, the boundary contracts and the guard configuration.

## The Iron Law

```
DEPENDENCIES POINT INWARD. DOMAIN DEPENDS ON NOTHING BUT THE STANDARD LIBRARY AND THE SHARED KERNEL.
```

## The shape

Per bounded context:

```
<context>/
  api               the ONLY part other contexts may use
  domain/           entities, value objects, aggregates, domain events, repository ports
  application/      use cases / command handlers; orchestrate domain + ports
  infrastructure/   adapters: ORM repositories, HTTP clients, ACL translators
```

Rules:
1. `domain` → standard library, the shared kernel. Nothing else: no ORM, no web framework, no serialization framework, no HTTP client, no environment or file access.
2. `application` → `domain`. It depends on **ports** (declared in `domain` or `application`), never on adapters.
3. `infrastructure` → `application`, `domain`, third-party libraries.
4. Other contexts → `<context>.api` only. `api` exposes commands, DTOs, query functions and integration events, **never domain objects**.
5. Wiring happens in one composition root, the only place that knows concrete adapters.

## Ports and adapters

Define what the domain *needs* in the domain's language, then adapt the world to it: repository ports, a unit of work, ACL translators, and in-memory fakes for tests. The variant has the code.

## What the plan must contain

Add these to the `superpowers:writing-plans` output.

**Plan header**, after the Architecture line:
```markdown
**Contexts touched:** Ordering (core), Billing (supporting)
**Glossary:** docs/domain/glossary.md (terms added: Refund, RefundPolicy)
**New boundaries:** billing infrastructure ACL for Stripe
**Boundary contracts:** <where the language keeps them> (contracts added: billing-domain-pure)
```

**Per task**, in the Files block:
```markdown
**Context / layer:** Billing / domain
**Aggregate:** Refund
**Invariants protected:** Refund amount ≤ captured amount; one Refund per Payment at a time
**Ports:** RefundRepository (new), PaymentGateway (existing)
```

**Ordering of tasks:** inside-out. Domain types and invariant tests first (pure, fast, no fakes needed), then application use cases against in-memory fakes, then infrastructure adapters with integration tests, then wiring. A task that writes an adapter before the port it implements exists is out of order.

**First task in a new context:** create the skeleton *and* add its boundary contracts *and* register it in the domain-powers config. The boundary exists before the code that might violate it.

## Integrating with the outside

Every external system (payment provider, legacy DB, partner API, even your own other service) gets an anti-corruption layer in `infrastructure/acl/<system>`: a translator that maps their types to yours, plus an adapter that implements your port. Their field names, enums, and error types stop at the ACL. Test the translator with recorded real payloads.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Using the ORM model in the domain saves a mapping layer" | It welds your invariants to your schema. Every migration becomes a domain change. Map. |
| "Other contexts can just use our domain types, it's one codebase" | Then you have one context, with extra folders. Expose DTOs via `api`. |
| "A port is ceremony for one implementation" | You have two: the real adapter and the in-memory fake your tests use. |
| "We'll add the boundary contract after it works" | After it works there'll be three violations to argue about. Add it first. |
| "This helper is needed in both contexts, put it in the shared kernel" | Shared kernel is for stable value types. Behaviour that might diverge gets duplicated. |
