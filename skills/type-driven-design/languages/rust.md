# Type-Driven Design: Rust (edition 2021+, clippy with `-D warnings`)

The compiler already rejects much of what a Python checker has to be configured for. The escapes in Rust are the places where code tells the compiler, or the reader, to take its word for it.

## Escapes

| Escape | Guard code | Instead |
|---|---|---|
| `unsafe` blocks, functions, impls, traits | `UNSAFE` | A safe API; if unavoidable, a small audited module in `infrastructure` |
| `.unwrap()`, `.expect(..)`, `panic!`, `todo!`, `unimplemented!`, `unreachable!` | `PANIC` | Return a `Result`, or change the types so the case cannot occur |
| `as` to a numeric type, `transmute` | `CAST` | `From` / `TryFrom`, or a value type that cannot hold the bad value |
| `dyn Any`, `std::any::Any`, `downcast` | `ANY` | An enum of the cases, a trait, or a generic |
| `#[allow(..)]`, `#![allow(..)]`, `#[expect(..)]` | `IGNORE` | Fix the code so the lint agrees |

The only accepted suppression is narrow and justified, outside `domain`:
`#[allow(clippy::large_enum_variant)] // domain-powers: allow generated protocol type`.

In tests, panics are fine: `clippy.toml` sets `allow-unwrap-in-tests`, `allow-expect-in-tests` and `allow-panic-in-tests` (see `domain-powers:quality-gates`), and the guard reports only suppressions there.

## The patterns in Rust

| Pattern | Rust |
|---|---|
| Value object | A struct with **private** fields and a `parse` / `new` constructor returning `Result<Self, E>`; derive `Clone, Debug, PartialEq, Eq, Hash` as needed |
| Distinct identity type | A newtype: `pub struct OrderId(Uuid);` |
| Enumeration / tagged union | `enum` (variants carry their own data) |
| Typed record at the edge | A `serde` DTO in `infrastructure`, then `TryFrom<Dto>` into the domain type |
| Result type | `Result<T, DomainError>` with an `enum DomainError` per aggregate |
| Exhaustive matching | `match` without a `_ =>` arm on domain enums, so a new variant fails to compile |
| Immutable collection | Private `Vec` exposed as `&[T]`; no `pub` collection fields |

## Where each tool belongs

| Layer | Allowed |
|---|---|
| `domain` | `std` and `core` (except `std::fs`, `std::net`, `std::process`, `std::env`), small pure crates such as `uuid` (types only), `rust_decimal`, `time`/`chrono` (types only, never `now()`), and the shared kernel. **No serde**: deriving `Deserialize` builds a value field by field without going through `parse`. **No async runtime**, no I/O crates. |
| `application` | Same as domain, plus ports (traits). Commands and results are plain structs and enums. |
| `infrastructure` / web | `serde`, `sqlx`/`diesel`, `reqwest`, `axum`, `tokio`, for parsing *external* data, then immediately converting with `TryFrom` into domain types. |

The guard's default forbidden list for a domain is in the pack card (`using-domain-powers/languages/rust.md`); add project-specific crates with `domain_forbidden`.

## Identity: newtype

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct OrderId(u128);

impl OrderId {
    pub fn new(raw: u128) -> Self {
        Self(raw)
    }
}
```

The application layer generates IDs (through a port) and passes them in; the domain never calls a random or clock function. `place(customer_id, order_id)` with swapped arguments is a compile error.

## Value object with rules: private fields and a parsing constructor

```rust
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Sku(String);

#[derive(Debug, PartialEq, Eq)]
pub enum SkuError {
    Malformed(String),
}

impl Sku {
    pub fn parse(raw: &str) -> Result<Self, SkuError> {
        let mut parts = raw.split('-');
        let ok = matches!(
            (parts.next(), parts.next(), parts.next()),
            (Some(a), Some(n), None)
                if a.len() == 3 && a.chars().all(|c| c.is_ascii_uppercase())
                && n.len() == 4 && n.chars().all(|c| c.is_ascii_digit())
        );
        if ok { Ok(Self(raw.to_owned())) } else { Err(SkuError::Malformed(raw.to_owned())) }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}
```

The field is private, so no code outside the module can build an unchecked `Sku`. Derive `Default` only if the default value is valid.

## Money (shared kernel candidate)

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Currency { Gbp, Eur }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Money { minor: i64, currency: Currency }

#[derive(Debug, PartialEq, Eq)]
pub enum MoneyError { Negative, CurrencyMismatch, Overflow }

impl Money {
    pub fn new(minor: i64, currency: Currency) -> Result<Self, MoneyError> {
        if minor < 0 { Err(MoneyError::Negative) } else { Ok(Self { minor, currency }) }
    }

    pub fn add(self, other: Self) -> Result<Self, MoneyError> {
        if self.currency != other.currency {
            return Err(MoneyError::CurrencyMismatch);
        }
        let minor = self.minor.checked_add(other.minor).ok_or(MoneyError::Overflow)?;
        Ok(Self { minor, currency: self.currency })
    }

    pub fn minor(self) -> i64 { self.minor }
    pub fn currency(self) -> Currency { self.currency }
}
```

Use `checked_*` arithmetic: an overflow is a business failure here, not a panic. Avoid `impl Add` when addition can fail; a method returning `Result` is honest.

## States with different data: enum or typestate

When the state is decided at run time (loaded from storage), use an enum:

```rust
pub enum Order {
    Draft(DraftOrder),
    Placed(PlacedOrder),
    Cancelled(CancelledOrder),
}
```

When each step consumes the previous state, use typestate: a method takes `self` by value and returns the next state, so the old state cannot be used again.

```rust
pub struct DraftOrder { id: OrderId, lines: Vec<OrderLine> }
pub struct PlacedOrder { id: OrderId, lines: Vec<OrderLine>, placed_at: Timestamp }

impl DraftOrder {
    pub fn place(self, at: Timestamp) -> Result<PlacedOrder, PlaceError> {
        if self.lines.is_empty() {
            return Err(PlaceError::NoLines);
        }
        Ok(PlacedOrder { id: self.id, lines: self.lines, placed_at: at })
    }
}
```

`PlacedOrder` has `placed_at`; `DraftOrder` doesn't have the field, so no `Option` and no check.

## Non-empty collections

```rust
pub struct NonEmpty<T> { head: T, tail: Vec<T> }

impl<T> NonEmpty<T> {
    pub fn from_vec(mut items: Vec<T>) -> Option<Self> {
        if items.is_empty() { return None; }
        let head = items.remove(0);
        Some(Self { head, tail: items })
    }
    pub fn first(&self) -> &T { &self.head }
    pub fn iter(&self) -> impl Iterator<Item = &T> { std::iter::once(&self.head).chain(&self.tail) }
}
```

## Expected failures: `Result` with a domain error enum

```rust
#[derive(Debug, PartialEq, Eq)]
pub enum CancelError {
    AlreadyShipped,
    AlreadyCancelled,
}

impl PlacedOrder {
    pub fn cancel(self, reason: CancelReason) -> Result<CancelledOrder, CancelError> { /* ... */ }
}
```

Callers `match` on the error. No `_ =>` arm: a new failure mode must be handled everywhere. Keep `Box<dyn Error>` and `anyhow` out of the domain; they erase which failures are possible.

## Parsing at the edge (infrastructure/web)

```rust
// infrastructure/http.rs
#[derive(serde::Deserialize)]
struct PlaceOrderDto { sku: String, quantity: u32 }

impl TryFrom<PlaceOrderDto> for PlaceOrder {
    type Error = ParseError;
    fn try_from(dto: PlaceOrderDto) -> Result<Self, Self::Error> {
        Ok(PlaceOrder {
            sku: Sku::parse(&dto.sku).map_err(ParseError::Sku)?,
            quantity: Quantity::try_from(dto.quantity).map_err(ParseError::Quantity)?,
        })
    }
}
```

The DTO derives serde; the domain type doesn't. The conversion is the one place raw data becomes domain data.

## Ports

- A port is a trait in `domain` (repositories) or `application` (other needs). Take `&self` and return `Result<_, PortError>`; an adapter's failure is an infrastructure error, not a panic.
- Inject ports as generics (`fn handle<R: OrderRepository>(repo: &R, ..)`) or `&dyn Trait`. Generics keep the fake and the real adapter equally fast in tests.
- Async: declare the port `async fn` only if the application is async end to end; the domain itself stays synchronous.

## Lints that make this bite

See `domain-powers:quality-gates` → `languages/rust/Cargo-template.toml`: `unsafe_code = "forbid"`, clippy `unwrap_used`, `expect_used`, `panic`, `todo`, `unimplemented`, `unreachable`, `as_conversions`, `indexing_slicing`, `wildcard_enum_match_arm`, `allow_attributes_without_reason`, plus the `pedantic` group, all denied by `-D warnings`.
