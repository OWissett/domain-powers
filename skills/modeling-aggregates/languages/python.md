# Aggregates: Python

## Domain events

```python
# domain/events.py
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime

@dataclass(frozen=True, slots=True, kw_only=True)
class OrderPlaced(DomainEvent):
    order_id: OrderId
    customer_id: CustomerId
    total: Money

@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCancelled(DomainEvent):
    order_id: OrderId
    reason: CancellationReason
```

Past tense, named in the ubiquitous language, immutable, carrying IDs and values, never whole aggregates.

## Aggregate root

```python
# domain/order.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Self


class OrderStatus(Enum):
    PLACED = auto()
    CANCELLED = auto()


@dataclass(frozen=True, slots=True)
class AlreadyCancelled:
    order_id: OrderId

@dataclass(frozen=True, slots=True)
class EmptyOrder: ...

CancelOutcome = OrderCancelled | AlreadyCancelled


class Order:
    __slots__ = ("_id", "_customer_id", "_lines", "_status", "_events")

    def __init__(self, *, _id: OrderId, customer_id: CustomerId,
                 lines: tuple[OrderLine, ...], status: OrderStatus) -> None:
        # Private: callers use place() or _rehydrate()
        self._id = _id
        self._customer_id = customer_id
        self._lines = lines
        self._status = status
        self._events: list[DomainEvent] = []

    # --- creation (enforces creation invariants) ---
    @classmethod
    def place(cls, order_id: OrderId, customer_id: CustomerId,
              lines: tuple[OrderLine, ...], now: datetime) -> Self | EmptyOrder:
        if not lines:
            return EmptyOrder()
        order = cls(_id=order_id, customer_id=customer_id, lines=lines,
                    status=OrderStatus.PLACED)
        order._record(OrderPlaced(occurred_at=now, order_id=order_id,
                                  customer_id=customer_id, total=order.total))
        return order

    # --- reconstitution (repositories only; no events, no checks re-run) ---
    @classmethod
    def _rehydrate(cls, *, _id: OrderId, customer_id: CustomerId,
                   lines: tuple[OrderLine, ...], status: OrderStatus) -> Self:
        return cls(_id=_id, customer_id=customer_id, lines=lines, status=status)

    # --- behaviour ---
    def cancel(self, reason: CancellationReason, now: datetime) -> CancelOutcome:
        if self._status is OrderStatus.CANCELLED:
            return AlreadyCancelled(self._id)
        self._status = OrderStatus.CANCELLED
        event = OrderCancelled(occurred_at=now, order_id=self._id, reason=reason)
        self._record(event)
        return event

    # --- read-only views ---
    @property
    def id(self) -> OrderId:
        return self._id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def total(self) -> Money:
        return sum_money(line.total for line in self._lines)

    # --- events ---
    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events, self._events = tuple(self._events), []
        return events
```

Notes:
- **Time is a parameter** (`now`), not `datetime.now()`. Aggregates stay deterministic and property-testable.
- `place()` returns `Self | EmptyOrder`: the caller must `match` on it, so an empty order can't silently be saved.
- A frozen-dataclass aggregate that returns a *new* instance per transition (`order.cancel() -> tuple[Order, OrderCancelled]`) is an equally good choice and even easier to property-test. Pick one style per codebase and record it in an ADR.

## Repository and events

The unit of work collects events from every aggregate it saw and publishes them **after** commit:

```python
class SqlAlchemyUnitOfWork:
    def commit(self) -> None:
        self._session.commit()
        for order in self.orders.seen:
            for event in order.pull_events():
                self._bus.publish(event)
```

If you need publish-exactly-once across a crash, use a transactional outbox (write events to an `outbox` table in the same transaction; a relay publishes them). Decide this in the plan, not mid-implementation.

## Policies (cross-aggregate reactions)

```python
# application/policies.py
def when_payment_captured_confirm_order(event: PaymentCapturedV1, uow: UnitOfWork,
                                        now: datetime) -> None:
    with uow:
        order = uow.orders.get(OrderId(event.order_id))
        if order is None:
            return  # log & dead-letter in infrastructure; not a domain concern
        match order.confirm(now):
            case OrderConfirmed():
                uow.commit()
            case AlreadyConfirmed() | OrderNotConfirmable():
                pass  # idempotent: events may be delivered twice
            case unreachable:
                assert_never(unreachable)
```

Handlers must be **idempotent**: integration events are delivered at least once.
