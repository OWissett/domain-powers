use super::events::OrderEvent;
use super::values::{CustomerId, OrderId, OrderLine, Timestamp};
use shared_kernel::{Currency, Money, MoneyError};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OrderStatus {
    Placed,
    Paid,
    Cancelled,
}

#[derive(Debug, PartialEq, Eq)]
pub enum PlaceError {
    NoLines,
    Money(MoneyError),
}

#[derive(Debug, PartialEq, Eq)]
pub enum CancelError {
    AlreadyCancelled,
    AlreadyPaid,
}

#[derive(Debug, PartialEq, Eq)]
pub enum ConfirmError {
    Cancelled,
}

/// The Order aggregate. Fields are private: every change goes through a root method.
#[derive(Clone, Debug)]
pub struct Order {
    id: OrderId,
    customer_id: CustomerId,
    lines: Vec<OrderLine>,
    status: OrderStatus,
    events: Vec<OrderEvent>,
}

impl Order {
    pub fn place(
        id: OrderId,
        customer_id: CustomerId,
        lines: Vec<OrderLine>,
        at: Timestamp,
    ) -> Result<Self, PlaceError> {
        if lines.is_empty() {
            return Err(PlaceError::NoLines);
        }
        let mut order = Self {
            id,
            customer_id,
            lines,
            status: OrderStatus::Placed,
            events: Vec::new(),
        };
        let total = order.total().map_err(PlaceError::Money)?;
        order.events.push(OrderEvent::Placed {
            order_id: id,
            customer_id,
            total,
            at,
        });
        Ok(order)
    }

    pub fn confirm_payment(&mut self, at: Timestamp) -> Result<(), ConfirmError> {
        match self.status {
            OrderStatus::Cancelled => Err(ConfirmError::Cancelled),
            OrderStatus::Paid => Ok(()), // idempotent: the same capture may arrive twice
            OrderStatus::Placed => {
                self.status = OrderStatus::Paid;
                self.events.push(OrderEvent::PaymentConfirmed {
                    order_id: self.id,
                    at,
                });
                Ok(())
            }
        }
    }

    pub fn cancel(&mut self, at: Timestamp) -> Result<(), CancelError> {
        match self.status {
            OrderStatus::Cancelled => Err(CancelError::AlreadyCancelled),
            OrderStatus::Paid => Err(CancelError::AlreadyPaid),
            OrderStatus::Placed => {
                self.status = OrderStatus::Cancelled;
                self.events.push(OrderEvent::Cancelled {
                    order_id: self.id,
                    customer_id: self.customer_id,
                    at,
                });
                Ok(())
            }
        }
    }

    pub fn id(&self) -> OrderId {
        self.id
    }

    pub fn status(&self) -> OrderStatus {
        self.status
    }

    pub fn total(&self) -> Result<Money, MoneyError> {
        self.lines
            .iter()
            .try_fold(Money::zero(Currency::Gbp), |sum, line| {
                sum.checked_add(line.total()?)
            })
    }

    pub fn pull_events(&mut self) -> Vec<OrderEvent> {
        std::mem::take(&mut self.events)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::values::{Quantity, Sku};
    use proptest::prelude::*;

    fn line() -> impl Strategy<Value = OrderLine> {
        ("[A-Z]{3}", 0u16..10_000, 1u32..100, 0i64..100_000).prop_map(|(a, n, q, p)| {
            OrderLine::new(
                Sku::parse(&format!("{a}-{n:04}")).expect("valid SKU"),
                Quantity::try_from(q).expect("positive"),
                Money::new(p, Currency::Gbp).expect("non-negative"),
            )
        })
    }

    #[derive(Clone, Debug)]
    enum Command {
        Cancel,
        ConfirmPayment,
    }

    fn command() -> impl Strategy<Value = Command> {
        prop_oneof![Just(Command::Cancel), Just(Command::ConfirmPayment)]
    }

    fn at() -> Timestamp {
        Timestamp::from_unix_seconds(1_700_000_000)
    }

    #[test]
    fn an_order_without_lines_cannot_be_placed() {
        let placed = Order::place(OrderId::new(1), CustomerId::new(2), Vec::new(), at());
        assert_eq!(placed.unwrap_err(), PlaceError::NoLines);
    }

    proptest! {
        #[test]
        fn order_invariants_hold_for_any_command_sequence(
            lines in prop::collection::vec(line(), 1..5),
            commands in prop::collection::vec(command(), 0..20),
        ) {
            let mut order = Order::place(OrderId::new(1), CustomerId::new(2), lines, at())
                .expect("lines present");
            let mut was_paid = false;
            for cmd in commands {
                let before = order.status();
                match cmd {
                    Command::Cancel => { let _ = order.cancel(at()); }
                    Command::ConfirmPayment => { let _ = order.confirm_payment(at()); }
                }
                was_paid |= order.status() == OrderStatus::Paid;
                // An order's total is never negative.
                prop_assert!(order.total().is_ok_and(|t| t.minor() >= 0));
                // A paid order is never cancelled.
                prop_assert!(!(was_paid && order.status() == OrderStatus::Cancelled));
                // A cancelled order stays cancelled.
                prop_assert!(before != OrderStatus::Cancelled || order.status() == OrderStatus::Cancelled);
            }
        }
    }
}
