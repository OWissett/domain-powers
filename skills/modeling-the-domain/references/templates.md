# Templates

## `docs/domain/glossary.md`

```markdown
# Glossary

Terms are scoped to a bounded context. The same word in two contexts is two entries.
**Avoid** lists words that must not be used for this concept; the domain-powers guard flags them in Markdown.

## Ordering

### Order
An agreement by a Customer to buy one or more Products at stated prices.
- **Not:** a Shipment (Fulfilment) or an Invoice (Billing).
- **Code:** `shop.ordering.domain.order.Order` (aggregate root)
- **Lifecycle:** Draft → Placed → Confirmed | Cancelled
- **Invariants:**
  - An Order has at least one OrderLine once Placed.
  - An Order's total equals the sum of its line totals and is never negative.
  - A Cancelled Order accepts no further commands.
- **Code aliases:** `Purchase` in `legacy/checkout.py` (do not extend)
- **Avoid:** purchase, basket order

### Place (an Order)
The Customer commits to the Order. Prices are frozen at this moment.
- **Command:** `PlaceOrder` → **Event:** `OrderPlaced`
```

## ADR (`docs/domain/decisions/NNNN-title.md`)

```markdown
# NNNN. <Decision>

Date: YYYY-MM-DD
Status: Accepted

## Context
What forces are at play, in domain terms.

## Decision
What we decided, e.g. "Billing consumes OrderPlaced instead of calling Ordering's domain."

## Consequences
What becomes easier, what becomes harder, and which guard/contract enforces it.
```

Write an ADR for every new context, every relationship pattern other than the default stance, and every suppression of a boundary rule that survives review.
