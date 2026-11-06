use shared_kernel::Money;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct PaymentId(u128);

impl PaymentId {
    pub fn new(raw: u128) -> Self {
        Self(raw)
    }

    pub fn value(self) -> u128 {
        self.0
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum CaptureError {
    ZeroAmount,
}

/// A captured payment for one order.
#[derive(Debug)]
pub struct Payment {
    id: PaymentId,
    order_ref: u128,
    amount: Money,
}

impl Payment {
    pub fn capture(id: PaymentId, order_ref: u128, amount: Money) -> Result<Self, CaptureError> {
        if amount.minor() == 0 {
            return Err(CaptureError::ZeroAmount);
        }
        Ok(Self {
            id,
            order_ref,
            amount,
        })
    }

    pub fn id(&self) -> PaymentId {
        self.id
    }

    pub fn order_ref(&self) -> u128 {
        self.order_ref
    }

    pub fn amount(&self) -> Money {
        self.amount
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use shared_kernel::Currency;

    #[test]
    fn a_zero_payment_is_refused() {
        let zero = Money::zero(Currency::Gbp);
        assert_eq!(
            Payment::capture(PaymentId::new(1), 7, zero).unwrap_err(),
            CaptureError::ZeroAmount
        );
    }
}
