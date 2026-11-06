use crate::domain::events::OrderEvent;
use crate::domain::order::{CancelError, Order, PlaceError};
use crate::domain::ports::{Clock, OrderIds, OrderRepository, RepositoryError};
use crate::domain::values::{CustomerId, OrderId, OrderLine};

pub struct PlaceOrder {
    pub customer_id: CustomerId,
    pub lines: Vec<OrderLine>,
}

#[derive(Debug)]
pub enum PlaceOrderError {
    Domain(PlaceError),
    Repository(RepositoryError),
}

pub fn place_order<R: OrderRepository, I: OrderIds, C: Clock>(
    cmd: PlaceOrder,
    orders: &R,
    ids: &I,
    clock: &C,
) -> Result<Vec<OrderEvent>, PlaceOrderError> {
    let mut order = Order::place(ids.next_id(), cmd.customer_id, cmd.lines, clock.now())
        .map_err(PlaceOrderError::Domain)?;
    let events = order.pull_events();
    orders.save(order).map_err(PlaceOrderError::Repository)?;
    Ok(events)
}

#[derive(Debug)]
pub enum CancelOrderError {
    UnknownOrder,
    Domain(CancelError),
    Repository(RepositoryError),
}

pub fn cancel_order<R: OrderRepository, C: Clock>(
    id: OrderId,
    orders: &R,
    clock: &C,
) -> Result<Vec<OrderEvent>, CancelOrderError> {
    let mut order = orders
        .get(id)
        .map_err(CancelOrderError::Repository)?
        .ok_or(CancelOrderError::UnknownOrder)?;
    order
        .cancel(clock.now())
        .map_err(CancelOrderError::Domain)?;
    let events = order.pull_events();
    orders.save(order).map_err(CancelOrderError::Repository)?;
    Ok(events)
}
