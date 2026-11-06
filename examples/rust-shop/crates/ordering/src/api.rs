//! Ordering's public surface: commands, DTOs and integration events, never domain types.

use crate::application::place_order::{
    cancel_order, place_order, CancelOrderError, PlaceOrder, PlaceOrderError,
};
use crate::application::policies::{when_payment_captured_confirm_order, PolicyError};
use crate::domain::events::OrderEvent;
use crate::domain::order::{CancelError, ConfirmError, OrderStatus, PlaceError};
use crate::domain::ports::OrderRepository;
use crate::domain::values::{CustomerId, OrderId, OrderLine, Quantity, Sku, ValueError};
use crate::infrastructure::memory::{InMemoryOrders, SequentialIds, SystemClock};
use billing::api::PaymentCapturedV1;
use shared_kernel::{Currency, Money, MoneyError};

pub struct LineRequest {
    pub sku: String,
    pub quantity: u32,
    pub unit_price_minor: i64,
}

pub struct PlaceOrderRequest {
    pub customer_id: u128,
    pub lines: Vec<LineRequest>,
}

/// Published when an order is placed. Versioned; never a domain type.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrderPlacedV1 {
    pub order_id: u128,
    pub customer_id: u128,
    pub total_minor: i64,
    pub currency: &'static str,
}

/// An order's lifecycle state, as other contexts see it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OrderStatusV1 {
    Placed,
    Paid,
    Cancelled,
}

#[derive(Debug, PartialEq, Eq)]
pub enum OrderingFailure {
    InvalidRequest(String),
    NoLines,
    UnknownOrder,
    AlreadyCancelled,
    AlreadyPaid,
    OrderCancelled,
    Storage(String),
}

/// The context's service handle, wired with in-memory adapters.
#[derive(Default)]
pub struct OrderingService {
    orders: InMemoryOrders,
    ids: SequentialIds,
}

impl OrderingService {
    /// Place an order.
    ///
    /// # Errors
    /// `InvalidRequest` for a malformed line, `NoLines` for an empty order.
    pub fn place_order(
        &self,
        request: &PlaceOrderRequest,
    ) -> Result<OrderPlacedV1, OrderingFailure> {
        let lines = request
            .lines
            .iter()
            .map(parse_line)
            .collect::<Result<Vec<_>, _>>()?;
        let cmd = PlaceOrder {
            customer_id: CustomerId::new(request.customer_id),
            lines,
        };
        let events =
            place_order(cmd, &self.orders, &self.ids, &SystemClock).map_err(|e| match e {
                PlaceOrderError::Domain(PlaceError::NoLines) => OrderingFailure::NoLines,
                PlaceOrderError::Domain(PlaceError::Money(m)) => money_failure(m),
                PlaceOrderError::Repository(r) => OrderingFailure::Storage(r.0),
            })?;
        events
            .iter()
            .find_map(placed_v1)
            .ok_or(OrderingFailure::Storage("no OrderPlaced event".to_owned()))
    }

    /// Cancel an order that has not been paid.
    ///
    /// # Errors
    /// `UnknownOrder`, `AlreadyCancelled` or `AlreadyPaid`.
    pub fn cancel_order(&self, order_id: u128) -> Result<(), OrderingFailure> {
        cancel_order(OrderId::new(order_id), &self.orders, &SystemClock)
            .map(|_| ())
            .map_err(|e| match e {
                CancelOrderError::UnknownOrder => OrderingFailure::UnknownOrder,
                CancelOrderError::Domain(CancelError::AlreadyCancelled) => {
                    OrderingFailure::AlreadyCancelled
                }
                CancelOrderError::Domain(CancelError::AlreadyPaid) => OrderingFailure::AlreadyPaid,
                CancelOrderError::Repository(r) => OrderingFailure::Storage(r.0),
            })
    }

    /// React to Billing's integration event.
    ///
    /// # Errors
    /// `UnknownOrder`, or `OrderCancelled` if the order was cancelled first.
    pub fn on_payment_captured(&self, event: &PaymentCapturedV1) -> Result<(), OrderingFailure> {
        when_payment_captured_confirm_order(event, &self.orders, &SystemClock)
            .map(|_| ())
            .map_err(|e| match e {
                PolicyError::UnknownOrder => OrderingFailure::UnknownOrder,
                PolicyError::Domain(ConfirmError::Cancelled) => OrderingFailure::OrderCancelled,
                PolicyError::Repository(r) => OrderingFailure::Storage(r.0),
            })
    }
}

impl OrderingService {
    /// Look up an order's status.
    ///
    /// # Errors
    /// `UnknownOrder` if there is no such order.
    pub fn order_status(&self, order_id: u128) -> Result<OrderStatusV1, OrderingFailure> {
        let order = self
            .orders
            .get(OrderId::new(order_id))
            .map_err(|r| OrderingFailure::Storage(r.0))?
            .ok_or(OrderingFailure::UnknownOrder)?;
        Ok(match order.status() {
            OrderStatus::Placed => OrderStatusV1::Placed,
            OrderStatus::Paid => OrderStatusV1::Paid,
            OrderStatus::Cancelled => OrderStatusV1::Cancelled,
        })
    }
}

fn parse_line(line: &LineRequest) -> Result<OrderLine, OrderingFailure> {
    let sku = Sku::parse(&line.sku).map_err(value_failure)?;
    let quantity = Quantity::try_from(line.quantity).map_err(value_failure)?;
    let price = Money::new(line.unit_price_minor, Currency::Gbp).map_err(money_failure)?;
    Ok(OrderLine::new(sku, quantity, price))
}

fn value_failure(error: ValueError) -> OrderingFailure {
    match error {
        ValueError::MalformedSku(raw) => OrderingFailure::InvalidRequest(format!("bad SKU {raw}")),
        ValueError::ZeroQuantity => OrderingFailure::InvalidRequest("zero quantity".to_owned()),
    }
}

fn money_failure(error: MoneyError) -> OrderingFailure {
    OrderingFailure::InvalidRequest(format!("bad amount: {error:?}"))
}

fn placed_v1(event: &OrderEvent) -> Option<OrderPlacedV1> {
    match event {
        OrderEvent::Placed {
            order_id,
            customer_id,
            total,
            at: _,
        } => Some(OrderPlacedV1 {
            order_id: order_id.value(),
            customer_id: customer_id.value(),
            total_minor: total.minor(),
            currency: total.currency().code(),
        }),
        OrderEvent::PaymentConfirmed { .. } | OrderEvent::Cancelled { .. } => None,
    }
}
