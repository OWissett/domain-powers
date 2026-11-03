import core
import pytest
from helpers import make_model, unit


def _order_invoice() -> tuple[list[dict[str, object]], list[tuple[str, str, int]]]:
    units = [
        unit("o.a", types=[("OrderHeader", False)]),
        unit("o.b", types=[("OrderLine", False)]),
        unit("o.c", types=[("OrderTotal", False)]),
        unit("i.a", types=[("InvoiceHeader", False)]),
        unit("i.b", types=[("InvoiceLine", False)]),
    ]
    edges = [
        ("o.a", "o.b", 2),
        ("o.b", "o.c", 2),
        ("o.c", "o.a", 1),
        ("i.a", "i.b", 2),
        ("o.a", "i.a", 1),
    ]
    return units, edges


def test_two_obvious_clusters() -> None:
    units, edges = _order_invoice()
    result = core.cluster_units(make_model(units, edges), {})
    assert result is not None
    assert [c.members for c in result.clusters] == [["i.a", "i.b"], ["o.a", "o.b", "o.c"]]
    assert result.separable
    assert result.unclustered == []


def test_shuffled_input_same_clusters() -> None:
    units, edges = _order_invoice()
    a = core.cluster_units(make_model(units, edges), {})
    b = core.cluster_units(make_model(units[::-1], edges[::-1]), {})
    assert a == b


def test_merge_singletons_heaviest_neighbour() -> None:
    labels = {"a": "A", "b": "A", "c": "C", "d": "D", "x": "X"}
    weights = {"x": {"a": 1.0, "c": 2.0}, "a": {"x": 1.0}, "c": {"x": 2.0}}
    assert core.merge_singletons(labels, weights)["x"] == "C"


def test_isolated_units_unclustered() -> None:
    model = make_model([unit("a"), unit("b"), unit("z")], [("a", "b", 1)])
    result = core.cluster_units(model, {})
    assert result is not None
    assert result.unclustered == ["z"]
    assert [c.members for c in result.clusters] == [["a", "b"]]


def test_single_cluster_not_separable() -> None:
    model = make_model([unit("a"), unit("b")], [("a", "b", 1)])
    result = core.cluster_units(model, {})
    assert result is not None
    assert not result.separable
    assert result.clusters[0].name == "a"


def test_naming_uses_tf_idf() -> None:
    units = [
        unit("o.a", types=[("OrderLine", False)]),
        unit("o.b", types=[("OrderLine", False), ("OrderItem", False)]),
        unit("i.a", types=[("InvoiceLine", False)]),
        unit("i.b", types=[("InvoiceLine", False)]),
    ]
    model = make_model(units, [("o.a", "o.b", 1), ("i.a", "i.b", 1)])
    result = core.cluster_units(model, {})
    assert result is not None
    names = {c.members[0]: c.terms for c in result.clusters}
    assert names["o.a"] == ["order", "item", "line"]
    assert names["i.a"] == ["invoice", "line"]


def test_cohesion() -> None:
    model = make_model(
        [unit("a"), unit("b"), unit("c")],
        [("a", "b", 1), ("b", "a", 1), ("b", "c", 1)],
        capabilities=["edges"],
    )
    weights = core.cluster_weights(model)
    assert weights["a"]["b"] == 2.0
    result = core.cluster_units(model, {})
    assert result is not None
    # a,b,c all join one cluster here; cohesion is 1.0 when nothing leaves it
    assert result.clusters[0].cohesion == 1.0
    units, edges = _order_invoice()
    full = core.cluster_units(make_model(units, edges), {})
    assert full is not None
    order = next(c for c in full.clusters if c.members[0] == "o.a")
    assert order.cohesion == pytest.approx(5 / 6)


def test_terms_only_without_edges() -> None:
    units = [
        unit("a", types=[("OrderLine", False)]),
        unit("b", types=[("OrderItem", False)]),
        unit("c", types=[("InvoiceRow", False)]),
        unit("d", types=[("InvoiceTotal", False)]),
    ]
    model = make_model(units, capabilities=["types"])
    result = core.cluster_units(model, {})
    assert result is not None
    assert [c.members for c in result.clusters] == [["a", "b"], ["c", "d"]]
    assert all(c.cohesion is None for c in result.clusters)


def test_edges_only_without_types() -> None:
    model = make_model([unit("a"), unit("b")], [("a", "b", 3)], capabilities=["edges"])
    result = core.cluster_units(model, {})
    assert result is not None
    assert result.clusters[0].terms == []
    assert result.clusters[0].name == "a"


def test_not_applicable_without_edges_and_types() -> None:
    na: core.NotApplicable = {}
    assert core.cluster_units(make_model([unit("a")], capabilities=[]), na) is None
    assert na == {"clusters": "missing capability: edges, types"}
