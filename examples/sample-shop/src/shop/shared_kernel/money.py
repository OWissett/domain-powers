from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Currency(Enum):
    GBP = 2
    JPY = 0

    @property
    def minor_units(self) -> int:
        return self.value


class CurrencyMismatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        exponent = self.amount.as_tuple().exponent
        if isinstance(exponent, int) and -exponent > self.currency.minor_units:
            raise ValueError("too many decimal places")

    @classmethod
    def from_minor(cls, minor: int, currency: Currency) -> Money:
        return cls(Decimal(minor).scaleb(-currency.minor_units), currency)

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(Decimal(0), currency)

    def __add__(self, other: Money) -> Money:
        if other.currency is not self.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def times(self, n: int) -> Money:
        return Money(self.amount * n, self.currency)
