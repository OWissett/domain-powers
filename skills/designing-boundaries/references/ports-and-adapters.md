# Ports and Adapters in Python

## Repository port (domain/ports.py)

```python
from typing import Protocol

from shop.ordering.domain.order import Order
from shop.ordering.domain.values import OrderId


class OrderRepository(Protocol):
    def get(self, order_id: OrderId) -> Order | None: ...
    def add(self, order: Order) -> None: ...
```

- One repository per **aggregate root**, never per table or per entity.
- Methods speak the domain language: `get`, `add`, and domain queries like `pending_for(customer_id)`. No `filter(**kwargs)`, no query builders.
- Returns domain objects, never ORM rows or dicts.

## Unit of work (application/unit_of_work.py)

```python
from types import TracebackType
from typing import Protocol, Self

from shop.ordering.domain.ports import OrderRepository


class UnitOfWork(Protocol):
    orders: OrderRepository

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def commit(self) -> None: ...
```

One aggregate modified per unit of work. If a use case must change two aggregates atomically, revisit the aggregate boundary (`domain-powers:modeling-aggregates`) before reaching for a bigger transaction.

## Application handler

```python
from dataclasses import dataclass

from shop.ordering.application.unit_of_work import UnitOfWork
from shop.ordering.domain.order import Order
from shop.ordering.domain.values import CustomerId, OrderId, OrderLineSpec


@dataclass(frozen=True, slots=True)
class PlaceOrder:
    order_id: OrderId
    customer_id: CustomerId
    lines: tuple[OrderLineSpec, ...]


def place_order(cmd: PlaceOrder, uow: UnitOfWork) -> None:
    with uow:
        order = Order.place(cmd.order_id, cmd.customer_id, cmd.lines)
        uow.orders.add(order)
        uow.commit()
```

Handlers contain no business rules. If you see an `if` about the domain in a handler, move it into the aggregate.

## In-memory fake (tests/…/fakes.py)

```python
class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[OrderId, Order] = {}

    def get(self, order_id: OrderId) -> Order | None:
        return self._orders.get(order_id)

    def add(self, order: Order) -> None:
        self._orders[order.id] = order
```

Structural typing means the fake satisfies `OrderRepository` without inheriting it, and mypy checks that it does when you pass it to `place_order`. Prefer fakes to `unittest.mock` for ports: a mock accepts any call, so it can't tell you the port contract broke.

## Anti-corruption layer (infrastructure/acl/stripe.py)

```python
from typing import Literal, TypedDict

from shop.billing.domain.payment import PaymentStatus
from shop.billing.domain.values import PaymentId
from shop.shared_kernel.money import Money


class _StripeCharge(TypedDict):          # their shape, private to the ACL
    id: str
    amount: int                           # minor units
    currency: str
    status: Literal["succeeded", "pending", "failed"]


_STATUS: dict[str, PaymentStatus] = {
    "succeeded": PaymentStatus.CAPTURED,
    "pending": PaymentStatus.PENDING,
    "failed": PaymentStatus.FAILED,
}


def to_domain(raw: _StripeCharge) -> tuple[PaymentId, Money, PaymentStatus]:
    return (
        PaymentId.parse(raw["id"]),
        Money.from_minor(raw["amount"], raw["currency"]),
        _STATUS[raw["status"]],
    )
```

Parse the raw payload into `_StripeCharge` at the very edge (pydantic or a TypedDict validator lives here, in infrastructure). The domain never sees `"succeeded"`.

## Integration events across contexts

Domain events stay inside their context. To tell another context something happened, the `application` layer translates domain events into **integration events**: plain frozen dataclasses defined in the publisher's `api.py`, carrying primitive or shared-kernel types only, versioned by name (`OrderPlacedV1`). Consumers handle them in their own `application` layer.
