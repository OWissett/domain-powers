use super::order::Order;
use super::values::{OrderId, Timestamp};

#[derive(Debug, PartialEq, Eq)]
pub struct RepositoryError(pub String);

/// Where orders live. One port per aggregate, in the domain's words.
pub trait OrderRepository {
    fn get(&self, id: OrderId) -> Result<Option<Order>, RepositoryError>;
    fn save(&self, order: Order) -> Result<(), RepositoryError>;
}

/// Hands out new order identities.
pub trait OrderIds {
    fn next_id(&self) -> OrderId;
}

/// The current time, so the domain never reads a clock itself.
pub trait Clock {
    fn now(&self) -> Timestamp;
}
