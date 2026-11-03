from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Self

from shop.ordering.domain.events import DomainEvent, OrderCancelled, OrderPlaced
from shop.ordering.domain.values import CustomerId, OrderId, OrderLine
from shop.shared_kernel.money import Money


class OrderStatus(Enum):
    PLACED = auto()
    CANCELLED = auto()


@dataclass(frozen=True, slots=True)
class EmptyOrder:
    pass


@dataclass(frozen=True, slots=True)
class AlreadyCancelled:
    order_id: OrderId


class Order:
    __slots__ = ("_customer_id", "_events", "_id", "_lines", "_status")

    def __init__(
        self,
        *,
        order_id: OrderId,
        customer_id: CustomerId,
        lines: tuple[OrderLine, ...],
        status: OrderStatus,
    ) -> None:
        self._id = order_id
        self._customer_id = customer_id
        self._lines = lines
        self._status = status
        self._events: list[DomainEvent] = []

    @classmethod
    def place(
        cls,
        order_id: OrderId,
        customer_id: CustomerId,
        lines: tuple[OrderLine, ...],
        now: datetime,
    ) -> Self | EmptyOrder:
        if not lines:
            return EmptyOrder()
        order = cls(
            order_id=order_id, customer_id=customer_id, lines=lines, status=OrderStatus.PLACED
        )
        order._events.append(
            OrderPlaced(
                occurred_at=now, order_id=order_id, customer_id=customer_id, total=order.total
            )
        )
        return order

    def cancel(self, now: datetime) -> OrderCancelled | AlreadyCancelled:
        if self._status is OrderStatus.CANCELLED:
            return AlreadyCancelled(self._id)
        self._status = OrderStatus.CANCELLED
        event = OrderCancelled(occurred_at=now, order_id=self._id)
        self._events.append(event)
        return event

    @property
    def id(self) -> OrderId:
        return self._id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def total(self) -> Money:
        first, *rest = self._lines
        total = first.total
        for line in rest:
            total = total + line.total
        return total

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events, self._events = tuple(self._events), []
        return events
