from typing import Protocol

from shop.ordering.domain.order import Order
from shop.ordering.domain.values import OrderId


class OrderRepository(Protocol):
    def get(self, order_id: OrderId) -> Order | None: ...
    def add(self, order: Order) -> None: ...
