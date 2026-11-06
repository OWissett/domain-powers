# Testing Invariants: Rust (proptest)

## Tooling by layer

| Layer | Tooling |
|---|---|
| Value objects | `proptest` (`proptest!` macro, `prop_assert!`) |
| Aggregates | `proptest` with a generated command sequence (below), or `proptest-state-machine` |
| Application | `#[test]` with in-memory fakes implementing the port traits |
| ACL / translators | `#[test]` on recorded payloads under `tests/fixtures/`, read with `include_str!` |
| Adapters | Integration tests in `tests/` against real infrastructure (testcontainers), one generic contract suite run against fake and real |
| Context `api` | Contract tests in the consumer crate, run in the provider's CI |
| Architecture | The compiler (private modules), `cargo deny check bans`, and the guard |

- Add `proptest` as a `[dev-dependencies]` entry of each context crate.
- Name each property after its glossary invariant: `order_total_is_never_negative`.
- proptest writes shrunk failures to `proptest-regressions/`. **Commit that directory**: it is the regression suite. For a case you want to read in code, also add a plain `#[test]` with the minimal input.
- Never lower `cases` to make a test pass, and never `#[ignore]` an invariant test.

## Shared strategies (tests/strategies.rs or a `strategies` module behind `#[cfg(test)]`)

```rust
use proptest::prelude::*;

pub fn sku() -> impl Strategy<Value = Sku> {
    ("[A-Z]{3}", 0u16..10_000).prop_map(|(a, n)| {
        Sku::parse(&format!("{a}-{n:04}")).expect("generator builds valid SKUs")
    })
}

pub fn money_gbp() -> impl Strategy<Value = Money> {
    (0i64..1_000_000).prop_map(|minor| Money::new(minor, Currency::Gbp).expect("non-negative"))
}

pub fn raw_bad_sku() -> impl Strategy<Value = String> {
    "\\PC*".prop_filter("not a valid SKU", |s| Sku::parse(s).is_err())
}
```

Generators go through the domain's own constructors, so they produce only valid values. `expect` is fine here: test code may panic, and `clippy.toml` allows it in tests.

## Value object: rejection and round trip

```rust
proptest! {
    #[test]
    fn sku_rejects_malformed_input(raw in raw_bad_sku()) {
        prop_assert!(Sku::parse(&raw).is_err());
    }

    #[test]
    fn sku_round_trips(sku in sku()) {
        prop_assert_eq!(Sku::parse(sku.as_str()), Ok(sku));
    }
}
```

## Algebraic laws

```rust
proptest! {
    #[test]
    fn money_addition_is_associative(a in money_gbp(), b in money_gbp(), c in money_gbp()) {
        let left = a.add(b).and_then(|ab| ab.add(c));
        let right = b.add(c).and_then(|bc| a.add(bc));
        prop_assert_eq!(left, right);
    }
}
```

## Aggregate: stateful invariant test

Generate a sequence of commands, apply each to the aggregate, and check every invariant after every step:

```rust
#[derive(Clone, Debug)]
enum Command { Cancel, ConfirmPayment }

fn command() -> impl Strategy<Value = Command> {
    prop_oneof![Just(Command::Cancel), Just(Command::ConfirmPayment)]
}

proptest! {
    #[test]
    fn order_invariants_hold_for_any_command_sequence(
        lines in prop::collection::vec(order_line(), 1..5),
        commands in prop::collection::vec(command(), 0..20),
    ) {
        let mut order = Order::place(order_id(), customer_id(), lines, at()).expect("lines present");
        for cmd in commands {
            let _ = match cmd {
                Command::Cancel => order.cancel(CancellationReason::CustomerRequest, at()).map(|_| ()),
                Command::ConfirmPayment => order.confirm_payment().map(|_| ()),
            };
            // invariants named in the glossary:
            prop_assert!(order.total().is_ok_and(|t| t.minor() >= 0));
            prop_assert!(!order.lines().is_empty());
        }
    }
}
```

Expected failures (`Err(CancelError::AlreadyCancelled)`) are part of the sequence; the invariants must hold after them too. For larger models with preconditions per command, use `proptest-state-machine` (a reference state machine plus the system under test).

## Port contract suite (same tests, fake and real adapter)

```rust
// tests/support/order_repository_contract.rs
pub fn added_order_can_be_got<R: OrderRepository>(repo: &R) {
    let mut order = placed_order();
    repo.save(&mut order).expect("save");
    let got = repo.get(order.id()).expect("get").expect("present");
    assert_eq!(got.id(), order.id());
}

// tests/memory_repository.rs
#[test]
fn memory_repository_honours_contract() {
    contract::added_order_can_be_got(&InMemoryOrders::default());
}

// tests/pg_repository.rs (integration, needs a database)
#[test]
fn pg_repository_honours_contract() {
    contract::added_order_can_be_got(&pg_orders());
}
```

If the fake passes and the real adapter fails (or the reverse), the fake has drifted from reality. Fix whichever is wrong.

## Settings

proptest reads the number of cases from the `PROPTEST_CASES` environment variable (default 256). The quality gate runs `cargo test --workspace` with `PROPTEST_CASES=500` in `scripts/check.sh`. Per test, when a property needs a different count for a stated reason:

```rust
proptest! {
    #![proptest_config(ProptestConfig::with_cases(1_000))]
    // ...
}
```
