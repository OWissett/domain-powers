use shared_kernel::{Money, MoneyError};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct OrderId(u128);

impl OrderId {
    pub fn new(raw: u128) -> Self {
        Self(raw)
    }

    pub fn value(self) -> u128 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct CustomerId(u128);

impl CustomerId {
    pub fn new(raw: u128) -> Self {
        Self(raw)
    }

    pub fn value(self) -> u128 {
        self.0
    }
}

/// Seconds since the Unix epoch, supplied by the application's clock port.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Timestamp(u64);

impl Timestamp {
    pub fn from_unix_seconds(seconds: u64) -> Self {
        Self(seconds)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ValueError {
    MalformedSku(String),
    ZeroQuantity,
}

/// A stock-keeping unit: three capital letters, a dash, four digits (`ABC-0042`).
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Sku(String);

impl Sku {
    pub fn parse(raw: &str) -> Result<Self, ValueError> {
        let mut parts = raw.split('-');
        let well_formed = matches!(
            (parts.next(), parts.next(), parts.next()),
            (Some(letters), Some(digits), None)
                if letters.len() == 3
                    && letters.chars().all(|c| c.is_ascii_uppercase())
                    && digits.len() == 4
                    && digits.chars().all(|c| c.is_ascii_digit())
        );
        if well_formed {
            Ok(Self(raw.to_owned()))
        } else {
            Err(ValueError::MalformedSku(raw.to_owned()))
        }
    }
}

/// A positive number of items.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Quantity(u32);

impl TryFrom<u32> for Quantity {
    type Error = ValueError;

    fn try_from(raw: u32) -> Result<Self, Self::Error> {
        if raw == 0 {
            Err(ValueError::ZeroQuantity)
        } else {
            Ok(Self(raw))
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrderLine {
    sku: Sku,
    quantity: Quantity,
    unit_price: Money,
}

impl OrderLine {
    pub fn new(sku: Sku, quantity: Quantity, unit_price: Money) -> Self {
        Self {
            sku,
            quantity,
            unit_price,
        }
    }

    pub fn total(&self) -> Result<Money, MoneyError> {
        self.unit_price.times(self.quantity.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        #[test]
        fn sku_round_trips(letters in "[A-Z]{3}", number in 0u16..10_000) {
            let raw = format!("{letters}-{number:04}");
            prop_assert_eq!(Sku::parse(&raw).map(|s| s.0), Ok(raw));
        }

        #[test]
        fn sku_rejects_malformed_input(raw in "\\PC*") {
            let shaped = raw.len() == 8 && raw.as_bytes().get(3) == Some(&b'-');
            prop_assume!(!shaped);
            prop_assert!(Sku::parse(&raw).is_err());
        }
    }

    #[test]
    fn quantity_is_never_zero() {
        assert_eq!(Quantity::try_from(0), Err(ValueError::ZeroQuantity));
    }
}
