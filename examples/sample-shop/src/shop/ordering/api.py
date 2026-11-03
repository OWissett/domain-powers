from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OrderPlacedV1:
    order_id: UUID
    total_minor: int
    currency: str
