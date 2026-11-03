from shop.ordering.domain.order import Order
from shop.ordering.domain.values import OrderId


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[OrderId, Order] = {}

    def get(self, order_id: OrderId) -> Order | None:
        return self._orders.get(order_id)

    def add(self, order: Order) -> None:
        self._orders[order.id] = order
