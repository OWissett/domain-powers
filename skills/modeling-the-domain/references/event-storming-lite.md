# Event Storming (lite), in text

Write it as a table in the design doc. One row per event, in timeline order.

| Actor | Command | Rule (can reject) | Event | Consistent data | Context |
|---|---|---|---|---|---|
| Customer | PlaceOrder | Cart not empty; every line's SKU is sellable; total ≥ minimum order | OrderPlaced | Order + its lines | Ordering |
| Payment provider (webhook) | CapturePayment | Amount equals order total; order not cancelled | PaymentCaptured | Payment | Billing |
| Policy: "when PaymentCaptured" | ConfirmOrder | Order is Placed (not Cancelled) | OrderConfirmed | Order | Ordering |
| Warehouse clerk | DispatchShipment | Order is Confirmed; all lines picked | ShipmentDispatched | Shipment | Fulfilment |

## Reading the table

- **Rule column**: each entry is an invariant and becomes a property-based test (`domain-powers:testing-invariants`).
- **Consistent data column**: data that must be consistent *in the same transaction* as the rule check. That is the aggregate. If two rows share consistent data, they are probably the same aggregate. If a rule needs data from two aggregates, either the boundary is wrong or the rule can be eventually consistent (ask the person which).
- **Policy rows** ("when X then Y") mark reactions. If they cross contexts, they become integration events plus a handler in the consuming context, never a direct call into the other context's domain.
- **Context column changes** mark integration points; each one needs a relationship in the context map.

## Hotspots

Mark with ⚠ any row where the person hesitated, contradicted themselves, or said "it depends". Those are where the model is still unknown. Resolve them before planning, or explicitly scope them out.
