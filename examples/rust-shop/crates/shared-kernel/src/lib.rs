//! Shared kernel: stable value types every context may use.

/// An ISO 4217 currency this shop trades in.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Currency {
    Gbp,
    Eur,
}

impl Currency {
    pub fn code(self) -> &'static str {
        match self {
            Currency::Gbp => "GBP",
            Currency::Eur => "EUR",
        }
    }
}

/// Why a `Money` value could not be built or combined.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MoneyError {
    Negative,
    CurrencyMismatch,
    Overflow,
}

/// A non-negative amount in minor units (pence, cents) of one currency.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Money {
    minor: i64,
    currency: Currency,
}

impl Money {
    /// # Errors
    /// `Negative` if `minor` is below zero.
    pub fn new(minor: i64, currency: Currency) -> Result<Self, MoneyError> {
        if minor < 0 {
            Err(MoneyError::Negative)
        } else {
            Ok(Self { minor, currency })
        }
    }

    pub fn zero(currency: Currency) -> Self {
        Self { minor: 0, currency }
    }

    /// # Errors
    /// `CurrencyMismatch` for different currencies, `Overflow` if the sum does not fit.
    pub fn checked_add(self, other: Self) -> Result<Self, MoneyError> {
        if self.currency != other.currency {
            return Err(MoneyError::CurrencyMismatch);
        }
        let minor = self
            .minor
            .checked_add(other.minor)
            .ok_or(MoneyError::Overflow)?;
        Ok(Self {
            minor,
            currency: self.currency,
        })
    }

    /// # Errors
    /// `Overflow` if the product does not fit.
    pub fn times(self, quantity: u32) -> Result<Self, MoneyError> {
        let minor = self
            .minor
            .checked_mul(i64::from(quantity))
            .ok_or(MoneyError::Overflow)?;
        Ok(Self {
            minor,
            currency: self.currency,
        })
    }

    pub fn minor(self) -> i64 {
        self.minor
    }

    pub fn currency(self) -> Currency {
        self.currency
    }
}
