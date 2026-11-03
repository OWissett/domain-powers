import core
import pytest
from helpers import make_model, unit


@pytest.mark.parametrize(
    "name,terms",
    [
        ("OrderLine", ["order", "line"]),
        ("HTTPServerError", ["http", "server", "error"]),
        ("order_line_item", ["order", "line", "item"]),
        ("OrderService", ["order"]),
        ("ID", []),
        ("Base64Encoder", ["encoder"]),
        ("OrderOrder", ["order"]),
    ],
)
def test_split_terms(name: str, terms: list[str]) -> None:
    assert core.split_terms(name) == terms


def test_stop_terms_has_the_spec_words() -> None:
    assert len(core.STOP_TERMS) == 21
    assert {"manager", "dto", "test"} <= core.STOP_TERMS


def test_scattered_needs_three_groups() -> None:
    model = make_model(
        [
            unit("a.x", types=[("Order", False), ("Line", False)]),
            unit("b.x", types=[("OrderItem", False), ("LineItem", False)]),
            unit("c.x", types=[("OrderRow", False)]),
        ]
    )
    na: core.NotApplicable = {}
    spread = core.term_spread(model, na)
    assert spread is not None
    assert spread.distinct == 4  # order, line, item, row
    assert spread.scattered == [core.ScatteredTerm("order", ["a", "b", "c"])]


def test_model_richness() -> None:
    model = make_model(
        [
            unit("m.a", hint="models", types=[("A", True), ("B", True), ("C", True), ("D", False)]),
            unit("s.a", hint="services", types=[("S", False), ("T", False)]),
            unit("o.a", types=[("Other", True)]),
        ]
    )
    r = core.model_richness(model, {})
    assert r == core.Richness(0.75, 4, 2)


def test_richness_share_none_without_model_types() -> None:
    model = make_model([unit("s.a", hint="services", types=[("S", False)])])
    r = core.model_richness(model, {})
    assert r == core.Richness(None, 0, 1)


def _entangled_model() -> core.Model:
    return make_model(
        [
            unit("m.a", hint="models", refs=["orm", "http"]),
            unit("m.b", hint="entities", refs=["orm"]),
            unit("m.c", hint="schemas"),
            unit("m.d", hint="domain"),
            unit("s.a", hint="services", refs=["orm"]),
        ]
    )


def test_entanglement_without_target() -> None:
    e = core.framework_entanglement(_entangled_model(), None, {})
    assert e == core.Entanglement(0.5, ["m.a", "m.b"], 3)


def test_entanglement_with_target_skips_generic() -> None:
    target = core.Target(
        (
            core.Context("core", "core", ("m.a", "m.c"), ()),
            core.Context("lib", "generic", ("m.b",), ()),
            core.Context("sup", "supporting", ("s.a",), ()),
        )
    )
    e = core.framework_entanglement(_entangled_model(), target, {})
    assert e == core.Entanglement(2 / 3, ["m.a", "s.a"], 3)


def test_entanglement_empty_scope() -> None:
    model = make_model([unit("s.a", hint="services", refs=["orm"])])
    assert core.framework_entanglement(model, None, {}) == core.Entanglement(None, [], 0)


def test_entanglement_target_overlap_propagates() -> None:
    target = core.Target(
        (core.Context("a", "core", ("m.*",), ()), core.Context("b", "core", ("m.a",), ()))
    )
    with pytest.raises(core.OverlapError):
        core.framework_entanglement(_entangled_model(), target, {})


def test_entanglement_target_needs_only_framework_refs() -> None:
    model = make_model([unit("m.a", refs=["x"])], capabilities=["framework_refs"])
    target = core.Target((core.Context("c", "core", ("m.*",), ()),))
    na: core.NotApplicable = {}
    assert core.framework_entanglement(model, target, na) == core.Entanglement(1.0, ["m.a"], 1)
    assert na == {}


def test_escape_totals() -> None:
    model = make_model(
        [
            unit("a.x", loc=500, escapes={"ANY": 2}),
            unit("a.y", loc=500, escapes={"ANY": 0, "CAST": 1}),
        ]
    )
    e = core.escape_totals(model, {})
    assert e == core.Escapes(3, 3.0, {"ANY": 2, "CAST": 1})


def test_escape_per_kloc_none_at_zero_loc() -> None:
    model = make_model([unit("a.x", loc=0, escapes={"ANY": 1})])
    assert core.escape_totals(model, {}) == core.Escapes(1, None, {"ANY": 1})


_ALL = sorted(core.CAPABILITIES)


@pytest.mark.parametrize(
    "missing,metric",
    [
        ("types", "terms"),
        ("data_only", "richness"),
        ("layer_hints", "richness"),
        ("framework_refs", "framework"),
        ("layer_hints", "framework"),
        ("escapes", "escapes"),
    ],
)
def test_not_applicable_per_capability(missing: str, metric: str) -> None:
    model = make_model([unit("a.x")], capabilities=[c for c in _ALL if c != missing])
    na: core.NotApplicable = {}
    results = [
        core.term_spread(model, na),
        core.model_richness(model, na),
        core.framework_entanglement(model, None, na),
        core.escape_totals(model, na),
    ]
    assert na[metric] == f"missing capability: {missing}"
    assert sum(r is None for r in results) == len(na)
