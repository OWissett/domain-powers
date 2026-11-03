from pathlib import Path

import core
import pytest
from helpers import make_model, unit

SPEC_TARGET = """
[contexts.ordering]
classification = "core"            # core | supporting | generic
units = ["shop.models.order*", "shop.services.checkout*"]
public = ["shop.services.checkout"]

[contexts.billing]
classification = "supporting"
units = ["shop.services.billing*", "shop.models.invoice*"]
public = ["shop.services.billing.api"]
"""


def _target(*contexts: tuple[str, tuple[str, ...], tuple[str, ...]]) -> core.Target:
    return core.Target(tuple(core.Context(n, "core", u, p) for n, u, p in contexts))


def _two_contexts() -> core.Target:
    return _target(("ordering", ("o.*",), ("o.api",)), ("billing", ("b.*",), ("b.api",)))


def test_parse_target() -> None:
    t = core.parse_target(SPEC_TARGET)
    assert [c.name for c in t.contexts] == ["billing", "ordering"]
    assert t.contexts[1] == core.Context(
        "ordering",
        "core",
        ("shop.models.order*", "shop.services.checkout*"),
        ("shop.services.checkout",),
    )


def test_bad_classification() -> None:
    text = '[contexts.a]\nclassification = "kernel"\nunits = ["x"]\n'
    with pytest.raises(core.TargetError, match="classification"):
        core.parse_target(text)


def test_missing_units() -> None:
    with pytest.raises(core.TargetError, match="units"):
        core.parse_target('[contexts.a]\nclassification = "core"\n')


def test_invalid_toml_is_target_error() -> None:
    with pytest.raises(core.TargetError):
        core.parse_target("[contexts.a\n")


def test_overlap_lists_units_and_contexts() -> None:
    m = make_model([unit("shop.x"), unit("shop.y")])
    t = _target(("a", ("shop.x", "shop.y"), ()), ("b", ("shop.x",), ()))
    with pytest.raises(core.OverlapError) as e:
        core.assign_units(m, t)
    assert e.value.overlaps == {"shop.x": ["a", "b"]}
    assert "shop.x" in str(e.value)


def test_distance() -> None:
    m = make_model(
        [unit("o.core"), unit("o.api"), unit("b.core"), unit("b.api"), unit("u.z")],
        [
            ("o.core", "b.api", 1),
            ("o.core", "b.core", 3),
            ("b.core", "o.core", 1),
            ("u.z", "o.core", 5),
        ],
    )
    d = core.distance(m, _two_contexts(), {})
    assert d is not None
    assert d.unassigned == ["u.z"]
    assert d.pairs == [
        core.ContextPair("billing", "ordering", 0, 1),
        core.ContextPair("ordering", "billing", 1, 3),
    ]
    assert d.context_cycles == [["billing", "ordering"]]
    assert [(w.source, w.target, w.count) for w in d.work_list] == [
        ("b.core", "o.core", 1),
        ("o.core", "b.core", 3),
    ]
    assert (
        d.work_list[0].source_context == "billing" and d.work_list[0].target_context == "ordering"
    )
    assert d.empty_contexts == []


def test_empty_context_is_reported() -> None:
    m = make_model([unit("o.core")])
    t = _target(("ordering", ("o.*",), ()), ("typo", ("zzz.*",), ()))
    d = core.distance(m, t, {})
    assert d is not None
    assert d.empty_contexts == ["typo"]


def test_target_json_ignores_table_order() -> None:
    reordered = "\n".join(reversed(SPEC_TARGET.strip().split("\n\n")))
    a = core.target_json(core.parse_target(SPEC_TARGET))
    assert a == core.target_json(core.parse_target(reordered))
    assert a == {
        "contexts": {
            "billing": {
                "classification": "supporting",
                "units": ["shop.services.billing*", "shop.models.invoice*"],
                "public": ["shop.services.billing.api"],
            },
            "ordering": {
                "classification": "core",
                "units": ["shop.models.order*", "shop.services.checkout*"],
                "public": ["shop.services.checkout"],
            },
        }
    }


def test_distance_needs_edges() -> None:
    m = make_model([unit("o.core")], capabilities=[])
    na: core.NotApplicable = {}
    assert core.distance(m, _two_contexts(), na) is None
    assert na["distance"] == "missing capability: edges"


def test_load_target(tmp_path: Path) -> None:
    path = tmp_path / "target.toml"
    path.write_text(SPEC_TARGET, encoding="utf-8")
    assert [c.name for c in core.load_target(path).contexts] == ["billing", "ordering"]
