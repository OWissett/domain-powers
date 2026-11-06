use crate::domain::events::OrderEvent;
use crate::domain::order::ConfirmError;
use crate::domain::ports::{Clock, OrderRepository, RepositoryError};
use crate::domain::values::OrderId;
use billing::api::PaymentCapturedV1;

#[derive(Debug)]
pub enum PolicyError {
    UnknownOrder,
    Domain(ConfirmError),
    Repository(RepositoryError),
}

/// When Billing captures a payment, confirm the order. Idempotent.
pub fn when_payment_captured_confirm_order<R: OrderRepository, C: Clock>(
    event: &PaymentCapturedV1,
    orders: &R,
    clock: &C,
) -> Result<Vec<OrderEvent>, PolicyError> {
    let mut order = orders
        .get(OrderId::new(event.order_id))
        .map_err(PolicyError::Repository)?
        .ok_or(PolicyError::UnknownOrder)?;
    order
        .confirm_payment(clock.now())
        .map_err(PolicyError::Domain)?;
    let events = order.pull_events();
    orders.save(order).map_err(PolicyError::Repository)?;
    Ok(events)
}
