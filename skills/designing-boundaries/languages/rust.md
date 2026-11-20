# Boundaries: Rust (workspace layout, visibility, cargo-deny, ports and adapters)

In plans, **Boundary contracts** points at the crate graph (`Cargo.toml` dependencies), module visibility, and `deny.toml [bans]`. Each context exposes `pub mod api`; the composition root is the binary crate. Ports are traits.

Rust gives you a boundary tool Python lacks: **the compiler**. A private module cannot be used from another crate at all, and a crate cannot use a crate it doesn't depend on. Put each boundary where the compiler can see it, and let the guard and `cargo deny` cover what it can't.

## Workspace tree

```
Cargo.toml                     [workspace], [workspace.lints], [workspace.metadata.domain-powers]
clippy.toml                    test allowances (see domain-powers:quality-gates)
deny.toml                      [bans]: frameworks only in listed crates
crates/
  shared-kernel/               Money, Currency: value types only; depends on nothing
    src/lib.rs
  ordering/                    one crate per context
    Cargo.toml                 [lints] workspace = true
    src/lib.rs                 pub mod api; mod domain; mod application; mod infrastructure;
    src/api.rs                 public surface: commands, DTOs, integration events, a service handle
    src/domain/
      mod.rs
      order.rs                 Order aggregate, OrderLine
      values.rs                OrderId, Quantity, Sku ...
      events.rs                OrderEvent (domain events)
      ports.rs                 OrderRepository trait
    src/application/
      mod.rs
      place_order.rs           PlaceOrder command + handler, generic over ports
    src/infrastructure/
      mod.rs
      memory.rs                in-memory adapters (also used by tests)
      pg.rs                    sqlx adapter
      acl/legacy_erp.rs
    tests/                     integration and contract tests
  billing/ ... same shape ...
  app/                         binary: composition root, HTTP entry points; uses contexts' api only
    src/main.rs
```

## What enforces each rule

| Rule | Enforced by |
|---|---|
| Other contexts use only `api` | **Compiler**: `domain`, `application`, `infrastructure` are private modules, so `billing::domain` does not resolve from another crate. The guard reports `CROSS-CTX` on the line as you write it. |
| Domain is pure | **Guard** (`DOMAIN-DEP`) on every edit and in the escape gate, because a module inside a crate that depends on `sqlx` could use it. For a core context, split the domain into its own crate (below) so **Cargo** enforces it too. |
| Application doesn't use its own infrastructure | **Guard** (`LAYER`). |
| Frameworks enter only through infrastructure-carrying crates | **cargo-deny** `[bans]` with `wrappers` (gate 4). |
| No cycles between contexts | **Cargo**: crate dependency cycles do not compile. |

## Splitting a core context's domain into its own crate

```
crates/
  ordering-domain/             depends on shared-kernel only
  ordering/                    depends on ordering-domain; holds api, application, infrastructure
```

The guard recognises `<context>-domain` (and `-application`, `-infrastructure`) as that context's layer. With the domain in its own crate, `cargo deny` can forbid every framework from it:

```toml
# deny.toml
[bans]
wildcards = "deny"
deny = [
  # frameworks: only the context crates (which hold infrastructure) and the binary may use them
  { crate = "sqlx", wrappers = ["ordering", "billing", "app"] },
  { crate = "reqwest", wrappers = ["billing"] },
  { crate = "axum", wrappers = ["app"] },
  { crate = "serde", wrappers = ["ordering", "billing", "app"] },
  # a context's domain crate: only its own context crate may depend on it
  { crate = "ordering-domain", wrappers = ["ordering"] },
]
```

`wrappers` lists the crates allowed to depend on the denied crate directly. Only list crates your workspace really depends on; cargo-deny reports unknown entries as warnings.

## Single-crate layout

A smaller project can keep one crate with a module per context (`src/ordering/{api.rs, domain/, application/, infrastructure/}`). Make each context's internals `pub(crate)` at most and re-export only `api`. The compiler then can't stop one context using another's internals (they share a crate), so the guard's `CROSS-CTX` is the boundary. Move to a workspace when a second team or a second binary appears.

## Edit-guard config

```toml
# Cargo.toml (workspace root), or [package.metadata.domain-powers] in a single crate
[workspace.metadata.domain-powers]
contexts = ["ordering", "billing"]   # context crate names (hyphens or underscores), or module names
shared = ["shared_kernel"]           # usable from anywhere, including domain
public_module = "api"                # the only module other contexts may use
domain_forbidden = ["legacy_sdk"]    # merged with the built-in list
```

Without this table the guard still checks type escapes and treats any file under a `domain` directory or module as domain.

## Ports and adapters

### Repository port (domain/ports.rs)

```rust
use super::order::Order;
use super::values::OrderId;

#[derive(Debug)]
pub struct RepositoryError(pub String);

pub trait OrderRepository {
    fn get(&self, id: OrderId) -> Result<Option<Order>, RepositoryError>;
    fn add(&self, order: Order) -> Result<(), RepositoryError>;
}
```

One trait per aggregate, in the domain's words. No `sqlx::Error` in the signature: the adapter maps its errors.

### Application handler (application/place_order.rs)

```rust
pub struct PlaceOrder { pub customer_id: CustomerId, pub lines: Vec<OrderLine> }

#[derive(Debug)]
pub enum PlaceOrderError { Domain(PlaceError), Repository(RepositoryError) }

pub fn place_order<R: OrderRepository, I: OrderIds, C: Clock>(
    cmd: PlaceOrder,
    orders: &R,
    ids: &I,
    clock: &C,
) -> Result<OrderId, PlaceOrderError> {
    let order = Order::place(ids.next(), cmd.customer_id, cmd.lines, clock.now())
        .map_err(PlaceOrderError::Domain)?;
    let id = order.id();
    orders.add(order).map_err(PlaceOrderError::Repository)?;
    Ok(id)
}
```

The handler orchestrates; the rules live in `Order::place`. IDs and time come through ports, so the domain stays deterministic.

### In-memory fake (infrastructure/memory.rs)

```rust
use std::cell::RefCell;
use std::collections::BTreeMap;

#[derive(Default)]
pub struct InMemoryOrders { rows: RefCell<BTreeMap<OrderId, Order>> }

impl OrderRepository for InMemoryOrders {
    fn get(&self, id: OrderId) -> Result<Option<Order>, RepositoryError> {
        Ok(self.rows.borrow().get(&id).cloned())
    }
    fn add(&self, order: Order) -> Result<(), RepositoryError> {
        self.rows.borrow_mut().insert(order.id(), order);
        Ok(())
    }
}
```

Use `Mutex` instead of `RefCell` if the adapter must be `Sync`. The fake lives in `infrastructure` (not `tests/`) so integration tests in other crates and the composition root's demo mode can use it.

### Anti-corruption layer (infrastructure/acl/stripe.rs)

```rust
#[derive(serde::Deserialize)]
struct StripeCharge { id: String, amount: i64, currency: String, status: String }

enum TranslateError { UnknownStatus(String), UnknownCurrency(String), Money(MoneyError) }

fn translate(charge: StripeCharge) -> Result<CapturedPayment, TranslateError> {
    let currency = match charge.currency.as_str() {
        "gbp" => Currency::Gbp,
        "eur" => Currency::Eur,
        other => return Err(TranslateError::UnknownCurrency(other.to_owned())),
    };
    let status = match charge.status.as_str() {
        "succeeded" => PaymentStatus::Captured,
        "failed" => PaymentStatus::Declined,
        other => return Err(TranslateError::UnknownStatus(other.to_owned())),
    };
    Ok(CapturedPayment {
        reference: PaymentReference::new(charge.id),
        amount: Money::new(charge.amount, currency).map_err(TranslateError::Money)?,
        status,
    })
}
```

Their field names and status strings stop here. An unknown status is an explicit error, never a default.

### Integration events across contexts (api.rs)

```rust
/// Published by Ordering for other contexts. Versioned; never a domain type.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrderPlacedV1 {
    pub order_id: u128,
    pub customer_id: u128,
    pub total_minor: i64,
    pub currency: String,
}
```

`api` maps `OrderEvent::Placed` to `OrderPlacedV1`. Add a field by publishing `V2` alongside `V1` until consumers move.
