from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NewType, Self
from uuid import UUID

from shop.shared_kernel.money import Money

OrderId = NewType("OrderId", UUID)
CustomerId = NewType("CustomerId", UUID)

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


@dataclass(frozen=True, slots=True)
class OrderLine:
    sku: Sku
    quantity: Quantity
    unit_price: Money

    @property
    def total(self) -> Money:
        return self.unit_price.times(self.quantity.value)
