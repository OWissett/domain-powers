from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from shop.ordering.domain.order import EmptyOrder, Order
from shop.ordering.domain.ports import OrderRepository
from shop.ordering.domain.values import CustomerId, OrderId, OrderLine


@dataclass(frozen=True, slots=True)
class PlaceOrder:
    order_id: OrderId
    customer_id: CustomerId
    lines: tuple[OrderLine, ...]


def place_order(cmd: PlaceOrder, repo: OrderRepository, now: datetime) -> Order | EmptyOrder:
    outcome = Order.place(cmd.order_id, cmd.customer_id, cmd.lines, now)
    match outcome:
        case Order():
            repo.add(outcome)
        case EmptyOrder():
            pass
        case _:
            assert_never(outcome)
    return outcome
