# Boundaries: Python (layout, import-linter contracts, ports and adapters)

In plans, **Boundary contracts** points at `pyproject.toml [tool.importlinter]`. Each context has an `api.py` module; the composition root is `<app>/bootstrap.py`. Ports are `typing.Protocol` classes.

## Package tree

```
pyproject.toml
src/shop/
  __init__.py
  bootstrap.py                 # composition root: builds adapters, injects into handlers
  shared_kernel/
    __init__.py
    money.py                   # Money, Currency: frozen value objects only
  ordering/
    __init__.py                # empty: don't re-export internals here
    api.py                     # public surface for other contexts
    domain/
      __init__.py
      order.py                 # Order aggregate, OrderLine entity
      values.py                # OrderId, Quantity, Sku ...
      events.py                # OrderPlaced, OrderCancelled (domain events)
      ports.py                 # OrderRepository Protocol
      errors.py                # domain exceptions / error types
    application/
      __init__.py
      place_order.py           # PlaceOrder command + handler
      unit_of_work.py          # UnitOfWork Protocol
    infrastructure/
      __init__.py
      sqlalchemy_repository.py
      acl/
        __init__.py
        legacy_erp.py
  billing/ ... same shape ...
  web/                         # framework entrypoints (FastAPI routers) — call <context>.api only
tests/
  ordering/
    unit/                      # domain + application with fakes: no I/O
    integration/               # adapters against real DB/containers
    contract/                  # api.py contract tests consumed by other contexts
  architecture/                # optional pytest-archon / import tests
```

## import-linter contracts

Put in `pyproject.toml`. Requires `import-linter >= 2.0` (module wildcards). Run with `lint-imports`.

```toml
[tool.importlinter]
root_package = "shop"
include_external_packages = true

# 1. Layers inside every context. Higher layers may import lower ones, never the reverse.
[[tool.importlinter.contracts]]
name = "context layers"
type = "layers"
containers = ["shop.ordering", "shop.billing", "shop.fulfilment"]
layers = [
    "(infrastructure)",   # parentheses = optional: a young context may lack it
    "(api)",
    "(application)",
    "domain",
]

# 2. Domain purity: no frameworks, ORMs, I/O libraries in any domain layer.
[[tool.importlinter.contracts]]
name = "domain is pure"
type = "forbidden"
source_modules = ["shop.*.domain"]
forbidden_modules = [
    "sqlalchemy", "django", "fastapi", "flask", "starlette",
    "pydantic", "requests", "httpx", "aiohttp", "boto3", "redis", "celery",
]

# 3. Contexts are independent except via each other's api module.
#    One forbidden contract per context keeps error messages readable.
[[tool.importlinter.contracts]]
name = "ordering does not reach into other contexts"
type = "forbidden"
source_modules = ["shop.ordering"]
forbidden_modules = [
    "shop.billing.domain", "shop.billing.application", "shop.billing.infrastructure",
    "shop.fulfilment.domain", "shop.fulfilment.application", "shop.fulfilment.infrastructure",
]

# 4. Framework entrypoints talk to contexts only through api.
[[tool.importlinter.contracts]]
name = "web uses public api only"
type = "forbidden"
source_modules = ["shop.web"]
forbidden_modules = ["shop.*.domain", "shop.*.application", "shop.*.infrastructure"]
```

Note on the layers contract: `infrastructure` is outermost (adapters may call the context's own `api`); `api` sits above `application` so it can call handlers and use `domain` types *internally*, but never adapters. Its **public signatures** must use DTOs. The reviewer checks that. import-linter cannot.

## Edit-guard config

The domain-powers edit hook reads this to know where contexts are:

```toml
[tool.domain-powers]
root_package = "shop"          # top-level import name
source_root = "src"            # directory containing the root package
contexts = ["ordering", "billing", "fulfilment"]
shared = ["shared_kernel"]     # importable from anywhere
public_module = "api"          # the only module other contexts may import
# Extra third-party modules banned from domain layers (merged with built-in list)
domain_forbidden = ["mylegacy_sdk"]
```

Without this table the guard still checks type escapes and any `*/domain/*.py` file for framework imports.

## Ports and adapters

### Repository port (domain/ports.py)

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

### Unit of work (application/unit_of_work.py)

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

### Application handler

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

### In-memory fake (tests/…/fakes.py)

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

### Anti-corruption layer (infrastructure/acl/stripe.py)

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

### Integration events across contexts

Domain events stay inside their context. To tell another context something happened, the `application` layer translates domain events into **integration events**: plain frozen dataclasses defined in the publisher's `api.py`, carrying primitive or shared-kernel types only, versioned by name (`OrderPlacedV1`). Consumers handle them in their own `application` layer.
