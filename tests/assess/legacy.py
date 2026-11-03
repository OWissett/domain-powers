"""A legacy, technically layered source tree and its slice, as source strings."""

LEGACY_TREE: dict[str, str] = {
    "shop/models/base.py": """\
from sqlalchemy import Column

from shop.utils.money import Money


class BaseModel:
    id: int
    column: Column
    price: Money
""",
    "shop/models/order.py": """\
from sqlalchemy import Column

from shop.models.base import BaseModel


class Order(BaseModel):
    number: int
    column: Column


class OrderLine(BaseModel):
    quantity: int
    sku: str
""",
    "shop/models/invoice.py": """\
from sqlalchemy import Column

from shop.models.base import BaseModel


class Invoice(BaseModel):
    number: int
    column: Column


class InvoiceLine(BaseModel):
    quantity: int
    sku: str
""",
    "shop/services/checkout.py": """\
from shop.models.base import BaseModel
from shop.models.order import Order
from shop.utils.money import Money


class OrderService:
    def place(self, order: Order, base: BaseModel, total: Money) -> int:
        return order.number + base.id + total.cents
""",
    "shop/services/billing.py": """\
from typing import Any

from shop.models.invoice import Invoice
from shop.models.order import Order
from shop.services.checkout import OrderService
from shop.utils.money import Money


class InvoiceService:
    def bill(
        self, invoice: Invoice, order: Order, service: OrderService, total: Money, extra: Any
    ) -> int:
        return invoice.number + order.number + total.cents
""",
    "shop/views/orders.py": """\
import flask

from shop.models.order import Order
from shop.services.checkout import OrderService


class OrderView:
    def show(self, service: OrderService, order: Order) -> str:
        return flask.render_template("order.html", order=order)  # type: ignore[attr-defined]
""",
    "shop/views/invoices.py": """\
import flask

from shop.models.invoice import Invoice
from shop.services.billing import InvoiceService


class InvoiceView:
    def show(self, service: InvoiceService, invoice: Invoice) -> str:
        return flask.render_template("invoice.html", invoice=invoice)
""",
    "shop/utils/money.py": """\
from shop.models.base import BaseModel


class Money:
    cents: int

    def owner(self, base: BaseModel) -> int:
        return base.id
""",
}

_MOVES = {
    "shop/models/invoice.py": "shop/billing/invoice.py",
    "shop/services/billing.py": "shop/billing/api.py",
    "shop/views/invoices.py": "shop/billing/views.py",
}
_RENAMES = {
    "shop.models.invoice": "shop.billing.invoice",
    "shop.services.billing": "shop.billing.api",
    "shop.views.invoices": "shop.billing.views",
}


def _slice() -> dict[str, str]:
    tree: dict[str, str] = {}
    for path, text in LEGACY_TREE.items():
        for old, new in _RENAMES.items():
            text = text.replace(old, new)
        if path == "shop/services/billing.py":
            text = text.replace("from shop.models.order import Order\n", "")
            text = text.replace("order: Order, ", "").replace("+ order.number ", "")
        tree[_MOVES.get(path, path)] = text
    return tree


SLICE_TREE: dict[str, str] = _slice()

TARGET_TOML = """\
[contexts.ordering]
classification = "core"
units = ["shop.models.order*", "shop.services.checkout*", "shop.views.orders*"]
public = ["shop.services.checkout"]

[contexts.billing]
classification = "supporting"
units = [
  "shop.models.invoice*", "shop.services.billing*", "shop.views.invoices*", "shop.billing*",
]
public = ["shop.services.billing", "shop.billing.api"]
"""
