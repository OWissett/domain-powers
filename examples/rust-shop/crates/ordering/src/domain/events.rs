use super::values::{CustomerId, OrderId, Timestamp};
use shared_kernel::Money;

/// Domain events recorded by the `Order` aggregate. Internal to Ordering.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OrderEvent {
    Placed {
        order_id: OrderId,
        customer_id: CustomerId,
        total: Money,
        at: Timestamp,
    },
    PaymentConfirmed {
        order_id: OrderId,
        at: Timestamp,
    },
    Cancelled {
        order_id: OrderId,
        customer_id: CustomerId,
        at: Timestamp,
    },
}
