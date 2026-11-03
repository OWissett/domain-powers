from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PaymentCapturedV1:
    order_id: UUID
