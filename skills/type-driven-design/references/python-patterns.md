# Python Type Patterns (Python ≥ 3.12, mypy --strict / pyright strict)

## Identity: NewType

```python
from typing import NewType
from uuid import UUID, uuid4

OrderId = NewType("OrderId", UUID)
CustomerId = NewType("CustomerId", UUID)

def new_order_id() -> OrderId:
    return OrderId(uuid4())
```

Use `NewType` when the concept has no rules beyond "is a distinct kind of X". Zero runtime cost. `place(customer_id, order_id)` with swapped arguments becomes a type error.

## Value object with rules: frozen dataclass + smart constructor

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Self

_SKU = re.compile(r"[A-Z]{3}-\d{4}")


@dataclass(frozen=True, slots=True)
class Sku:
    value: str

    def __post_init__(self) -> None:
        if not _SKU.fullmatch(self.value):
            raise ValueError(f"invalid SKU: {self.value!r}")

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip().upper())


@dataclass(frozen=True, slots=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("quantity must be positive")

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(self.value + other.value)
```

- `__post_init__` makes the invariant hold **for every construction path**, including tests and deserialisation.
- Raising here is correct: an invalid value object is a programming error *inside* the boundary. At the edge, catch `ValueError` from `parse` and turn it into a 4xx / validation result.
- Behaviour lives on the value (`__add__`, `Money.allocate`), not in helpers.

## Money (shared kernel candidate)

```python
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency          # an Enum

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        exponent = self.amount.as_tuple().exponent
        # exponent is int | Literal["n", "N", "F"]; is_finite() rules out the literals,
        # and isinstance proves it to the checker. No cast, no ignore.
        if isinstance(exponent, int) and -exponent > self.currency.minor_units:
            raise ValueError("too many decimal places")

    def __add__(self, other: Money) -> Money:
        if other.currency is not self.currency:
            raise CurrencyMismatch(self.currency, other.currency)
        return Money(self.amount + other.amount, self.currency)
```

When the checker objects, narrow (`isinstance`, `match`, a parse) until it agrees. That is how the guard wants you to respond.

## States with different data: union of dataclasses (typestate)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never


@dataclass(frozen=True, slots=True)
class Draft:
    lines: tuple[OrderLine, ...]

@dataclass(frozen=True, slots=True)
class Placed:
    lines: tuple[OrderLine, ...]   # non-empty, enforced by place()
    placed_at: datetime

@dataclass(frozen=True, slots=True)
class Cancelled:
    reason: CancellationReason
    cancelled_at: datetime

OrderState = Draft | Placed | Cancelled


def can_ship(state: OrderState) -> bool:
    match state:
        case Placed():
            return True
        case Draft() | Cancelled():
            return False
        case _:
            assert_never(state)
```

Add `Refunded` to `OrderState` and every `match` without a case fails type-checking. That is the point.

## Non-empty collections

```python
@dataclass(frozen=True, slots=True)
class NonEmpty[T]:
    head: T
    tail: tuple[T, ...] = ()

    @classmethod
    def of(cls, items: Sequence[T]) -> Self | None:
        return cls(items[0], tuple(items[1:])) if items else None

    def __iter__(self) -> Iterator[T]:
        yield self.head
        yield from self.tail
```

## Expected failures: result unions

Prefer domain-named outcomes over a generic Result library:

```python
@dataclass(frozen=True, slots=True)
class OrderPlaced:            # also the domain event
    order_id: OrderId
    total: Money

@dataclass(frozen=True, slots=True)
class EmptyCart: ...

@dataclass(frozen=True, slots=True)
class SkuNotSellable:
    sku: Sku

PlaceOrderOutcome = OrderPlaced | EmptyCart | SkuNotSellable
```

The caller `match`es with `assert_never`, so the web layer can't forget to map `SkuNotSellable` to a response. Use a generic `Ok[T] | Err[E]` (small, hand-written) only where outcomes really are generic.

## Parsing at the edge (infrastructure/web)

```python
from pydantic import BaseModel, ConfigDict

class PlaceOrderBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    customer_id: UUID
    lines: list[LineBody]

def to_command(body: PlaceOrderBody) -> PlaceOrder:      # the parse step
    return PlaceOrder(
        order_id=new_order_id(),
        customer_id=CustomerId(body.customer_id),
        lines=tuple(OrderLineSpec(Sku.parse(l.sku), Quantity(l.qty)) for l in body.lines),
    )
```

pydantic in `strict=True` mode, at the edge only. The command is all domain types; nothing behind it re-checks.

## Typing ports and callables

- Ports: `typing.Protocol`. Add `@runtime_checkable` only if you need `isinstance`, which you usually don't.
- Callbacks: `Callable[[OrderPlaced], None]`, never bare `Callable`.
- Generic repositories are a smell; one Protocol per aggregate.

## Checker settings that make this bite

See `domain-powers:quality-gates` → `references/pyproject-template.toml`: `mypy --strict` plus `warn_unreachable`, `enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool", "possibly-undefined"]`, and ruff rules `ANN`, `ANN401` (no `Any`), `PGH003` (no blanket ignores), `TC`, `FBT` (boolean trap), `PLR2004` (magic values).
