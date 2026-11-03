# Hypothesis Patterns for Domain Code

## Shared strategies (tests/strategies.py)

```python
from decimal import Decimal

from hypothesis import strategies as st

from shop.ordering.domain.values import Quantity, Sku
from shop.shared_kernel.money import Currency, Money

skus = st.from_regex(r"[A-Z]{3}-\d{4}", fullmatch=True).map(Sku)
quantities = st.integers(min_value=1, max_value=10_000).map(Quantity)

def money(currency: Currency = Currency.GBP, *, min_minor: int = 0) -> st.SearchStrategy[Money]:
    return st.integers(min_value=min_minor, max_value=10**9).map(
        lambda minor: Money.from_minor(minor, currency)
    )

st.register_type_strategy(Sku, skus)
st.register_type_strategy(Quantity, quantities)
```

## Value object: rejection and round-trip

```python
from hypothesis import example, given, strategies as st
import pytest

@given(st.text())
@example("abc-1234")      # lower-case: parse() normalises, constructor must not accept
def test_sku_constructor_rejects_anything_not_matching_format(raw: str) -> None:
    if re.fullmatch(r"[A-Z]{3}-\d{4}", raw):
        assert Sku(raw).value == raw
    else:
        with pytest.raises(ValueError):
            Sku(raw)

@given(skus)
def test_sku_parse_round_trips(sku: Sku) -> None:
    assert Sku.parse(sku.value) == sku
```

## Algebraic laws

```python
@given(money(), money(), money())
def test_money_addition_is_associative(a: Money, b: Money, c: Money) -> None:
    assert (a + b) + c == a + (b + c)

@given(money(), st.integers(min_value=1, max_value=50))
def test_allocation_never_loses_a_penny(total: Money, parts: int) -> None:
    assert sum_money(total.allocate(parts)) == total
```

## Aggregate: stateful invariant test

```python
from datetime import UTC, datetime

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

NOW = datetime(2026, 1, 1, tzinfo=UTC)

class OrderMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.order: Order | None = None

    @rule(lines=st.lists(st.builds(OrderLine), min_size=0, max_size=5))
    def place(self, lines: list[OrderLine]) -> None:
        match Order.place(new_order_id(), new_customer_id(), tuple(lines), NOW):
            case Order() as order:
                self.order = order
            case EmptyOrder():
                assert not lines

    @precondition(lambda self: self.order is not None)
    @rule(reason=st.sampled_from(CancellationReason))
    def cancel(self, reason: CancellationReason) -> None:
        assert self.order is not None
        self.order.cancel(reason, NOW)

    @invariant()
    def total_is_never_negative(self) -> None:          # glossary: Order invariant 2
        if self.order is not None:
            assert self.order.total.amount >= 0

    @invariant()
    def cancelled_is_terminal(self) -> None:            # glossary: Order invariant 3
        if self.order is not None and self.order.status is OrderStatus.CANCELLED:
            assert isinstance(self.order.cancel(CancellationReason.CUSTOMER, NOW), AlreadyCancelled)

TestOrderMachine = OrderMachine.TestCase
```

## Port contract suite (same tests, fake and real adapter)

```python
import pytest

@pytest.fixture(params=["fake", "sqlalchemy"])
def repo(request: pytest.FixtureRequest, db_session: Session) -> OrderRepository:
    if request.param == "fake":
        return InMemoryOrderRepository()
    return SqlAlchemyOrderRepository(db_session)

def test_added_order_can_be_got(repo: OrderRepository, placed_order: Order) -> None:
    repo.add(placed_order)
    got = repo.get(placed_order.id)
    assert got is not None and got.id == placed_order.id
```

If the fake passes and the real adapter fails (or vice versa), the fake has drifted from reality. Fix whichever is wrong.

## Settings

```python
# tests/conftest.py
from hypothesis import HealthCheck, settings

settings.register_profile("ci", max_examples=500, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("dev", max_examples=50)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
```
