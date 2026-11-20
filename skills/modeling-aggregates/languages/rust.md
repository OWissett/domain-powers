# Aggregates: Rust

## Domain events

```rust
// domain/events.rs
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OrderEvent {
    Placed { order_id: OrderId, customer_id: CustomerId, total: Money, at: Timestamp },
    Cancelled { order_id: OrderId, reason: CancellationReason, at: Timestamp },
}
```

One enum per aggregate keeps every event a `match` away from being handled. Events are internal to the context; integration events for other contexts live in its `api` module, versioned, and are mapped from these.

## Aggregate root

```rust
// domain/order.rs
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OrderStatus { Placed, Cancelled }

#[derive(Debug, PartialEq, Eq)]
pub enum PlaceError { NoLines, Money(MoneyError) }

#[derive(Debug, PartialEq, Eq)]
pub enum CancelError { AlreadyCancelled }

#[derive(Debug)]
pub struct Order {
    id: OrderId,
    customer_id: CustomerId,
    lines: Vec<OrderLine>,
    status: OrderStatus,
    events: Vec<OrderEvent>,
}

impl Order {
    // --- creation (enforces creation invariants) ---
    pub fn place(
        id: OrderId,
        customer_id: CustomerId,
        lines: Vec<OrderLine>,
        at: Timestamp,
    ) -> Result<Self, PlaceError> {
        if lines.is_empty() {
            return Err(PlaceError::NoLines);
        }
        let mut order = Self { id, customer_id, lines, status: OrderStatus::Placed, events: Vec::new() };
        let total = order.total().map_err(PlaceError::Money)?;
        order.events.push(OrderEvent::Placed { order_id: id, customer_id, total, at });
        Ok(order)
    }

    // --- reconstitution (repositories only; no events, no checks re-run) ---
    #[doc(hidden)]
    pub fn rehydrate(id: OrderId, customer_id: CustomerId, lines: Vec<OrderLine>, status: OrderStatus) -> Self {
        Self { id, customer_id, lines, status, events: Vec::new() }
    }

    // --- behaviour ---
    pub fn cancel(&mut self, reason: CancellationReason, at: Timestamp) -> Result<(), CancelError> {
        match self.status {
            OrderStatus::Cancelled => Err(CancelError::AlreadyCancelled),
            OrderStatus::Placed => {
                self.status = OrderStatus::Cancelled;
                self.events.push(OrderEvent::Cancelled { order_id: self.id, reason, at });
                Ok(())
            }
        }
    }

    // --- read-only views ---
    pub fn id(&self) -> OrderId { self.id }
    pub fn status(&self) -> OrderStatus { self.status }
    pub fn lines(&self) -> &[OrderLine] { &self.lines }

    pub fn total(&self) -> Result<Money, MoneyError> {
        self.lines.iter().try_fold(Money::zero(Currency::Gbp), |sum, line| sum.checked_add(line.total()?))
    }

    // --- events ---
    pub fn pull_events(&mut self) -> Vec<OrderEvent> {
        std::mem::take(&mut self.events)
    }
}
```

Notes:
- **Fields are private.** Only methods in this module can change them, so the invariants hold for every caller. Don't derive `Default` or add a public struct literal path.
- **Time is a parameter** (`at`), never `SystemTime::now()`. Aggregates stay deterministic and property-testable.
- `place` returns `Result`: the caller must handle `NoLines`, so an empty order can't silently be saved.
- `rehydrate` is public because the repository lives in another module. Mark it `#[doc(hidden)]` and let the reviewer check that only repositories call it, or put the repository adapter behind a `pub(crate)` constructor if it lives in the same crate.
- A consuming style (`fn cancel(self, ..) -> Result<(Order, OrderEvent), CancelError>`) or typestate (`PlacedOrder::cancel(self) -> CancelledOrder`) is an equally good choice and even easier to property-test. Pick one style per codebase and record it in an ADR.

## Repository and events

```rust
// domain/ports.rs
pub trait OrderRepository {
    fn get(&self, id: OrderId) -> Result<Option<Order>, RepositoryError>;
    fn save(&self, order: &mut Order) -> Result<Vec<OrderEvent>, RepositoryError>;
}
```

`save` persists the aggregate and returns the events it pulled, so the application layer publishes them **after** commit. If you need publish-exactly-once across a crash, use a transactional outbox (write events to an `outbox` table in the same transaction; a relay publishes them). Decide this in the plan, not mid-implementation.

## Policies (cross-aggregate reactions)

```rust
// application/policies.rs
pub fn when_payment_captured_confirm_order<R: OrderRepository>(
    event: &billing::api::PaymentCapturedV1,
    orders: &R,
) -> Result<(), PolicyError> {
    let Some(mut order) = orders.get(OrderId::new(event.order_id))? else {
        return Err(PolicyError::UnknownOrder);
    };
    order.confirm_payment()?;
    orders.save(&mut order)?;
    Ok(())
}
```

The policy consumes another context's *integration event* from its `api` module and issues a command to one aggregate. Make it idempotent: receiving the same event twice must leave the same state (check the current status before acting).
