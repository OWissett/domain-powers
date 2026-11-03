from dataclasses import dataclass
from typing import NewType
from uuid import UUID

from shop.shared_kernel.money import Money

PaymentId = NewType("PaymentId", UUID)


@dataclass(frozen=True, slots=True)
class Payment:
    payment_id: PaymentId
    amount: Money
