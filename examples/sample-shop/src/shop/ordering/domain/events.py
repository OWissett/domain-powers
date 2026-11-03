from dataclasses import dataclass
from datetime import datetime

from shop.ordering.domain.values import CustomerId, OrderId
from shop.shared_kernel.money import Money


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderPlaced:
    occurred_at: datetime
    order_id: OrderId
    customer_id: CustomerId
    total: Money


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCancelled:
    occurred_at: datetime
    order_id: OrderId


DomainEvent = OrderPlaced | OrderCancelled
