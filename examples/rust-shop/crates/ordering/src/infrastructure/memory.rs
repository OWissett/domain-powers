//! In-memory adapters: used by tests and by the binary's demo mode.

use crate::domain::order::Order;
use crate::domain::ports::{Clock, OrderIds, OrderRepository, RepositoryError};
use crate::domain::values::{OrderId, Timestamp};
use std::cell::{Cell, RefCell};
use std::collections::BTreeMap;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Default)]
pub struct InMemoryOrders {
    rows: RefCell<BTreeMap<OrderId, Order>>,
}

impl OrderRepository for InMemoryOrders {
    fn get(&self, id: OrderId) -> Result<Option<Order>, RepositoryError> {
        Ok(self.rows.borrow().get(&id).cloned())
    }

    fn save(&self, order: Order) -> Result<(), RepositoryError> {
        self.rows.borrow_mut().insert(order.id(), order);
        Ok(())
    }
}

#[derive(Default)]
pub struct SequentialIds {
    last: Cell<u128>,
}

impl OrderIds for SequentialIds {
    fn next_id(&self) -> OrderId {
        let next = self.last.get().saturating_add(1);
        self.last.set(next);
        OrderId::new(next)
    }
}

pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> Timestamp {
        let seconds = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |elapsed| elapsed.as_secs());
        Timestamp::from_unix_seconds(seconds)
    }
}
