//! Invariants of `Money`, named after the glossary.

use proptest::prelude::*;
use shared_kernel::{Currency, Money, MoneyError};

fn money_gbp() -> impl Strategy<Value = Money> {
    (0i64..1_000_000_000)
        .prop_filter_map("valid money", |minor| Money::new(minor, Currency::Gbp).ok())
}

proptest! {
    #[test]
    fn money_is_never_negative(minor in i64::MIN..0) {
        prop_assert_eq!(Money::new(minor, Currency::Gbp), Err(MoneyError::Negative));
    }

    #[test]
    fn money_addition_is_associative(a in money_gbp(), b in money_gbp(), c in money_gbp()) {
        let left = a.checked_add(b).and_then(|ab| ab.checked_add(c));
        let right = b.checked_add(c).and_then(|bc| a.checked_add(bc));
        prop_assert_eq!(left, right);
    }

    #[test]
    fn money_in_different_currencies_never_adds(a in money_gbp(), minor in 0i64..1_000) {
        let eur = Money::new(minor, Currency::Eur).expect("non-negative");
        prop_assert_eq!(a.checked_add(eur), Err(MoneyError::CurrencyMismatch));
    }
}
