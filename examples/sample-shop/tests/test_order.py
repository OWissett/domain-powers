from datetime import UTC, datetime
from uuid import uuid4

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from shop.ordering.application.place_order import PlaceOrder, place_order
from shop.ordering.domain.order import AlreadyCancelled, EmptyOrder, Order, OrderStatus
from shop.ordering.domain.values import CustomerId, OrderId, OrderLine, Quantity, Sku
from shop.ordering.infrastructure.memory import InMemoryOrderRepository
from shop.shared_kernel.money import Currency, Money

NOW = datetime(2026, 1, 1, tzinfo=UTC)
skus = st.from_regex(r"[A-Z]{3}-\d{4}", fullmatch=True).map(Sku)
lines = st.builds(
    OrderLine,
    sku=skus,
    quantity=st.integers(1, 100).map(Quantity),
    unit_price=st.integers(0, 10**6).map(lambda m: Money.from_minor(m, Currency.GBP)),
)


class OrderMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.repo = InMemoryOrderRepository()
        self.order: Order | None = None

    @rule(ls=st.lists(lines, max_size=4))
    def place(self, ls: list[OrderLine]) -> None:
        cmd = PlaceOrder(OrderId(uuid4()), CustomerId(uuid4()), tuple(ls))
        match place_order(cmd, self.repo, NOW):
            case Order() as order:
                self.order = order
            case EmptyOrder():
                assert not ls

    @precondition(lambda self: self.order is not None)
    @rule()
    def cancel(self) -> None:
        assert self.order is not None
        self.order.cancel(NOW)

    @invariant()
    def total_is_never_negative(self) -> None:
        if self.order is not None:
            assert self.order.total.amount >= 0

    @invariant()
    def cancelled_is_terminal(self) -> None:
        if self.order is not None and self.order.status is OrderStatus.CANCELLED:
            assert isinstance(self.order.cancel(NOW), AlreadyCancelled)


TestOrderMachine = OrderMachine.TestCase
