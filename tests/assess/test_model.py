import json
from pathlib import Path

import core
import pytest
from helpers import make_model, unit


def _raw(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": core.MODEL_SCHEMA,
        "language": "python",
        "root": "src",
        "capabilities": [],
        "units": [],
        "edges": [],
        "skipped": [],
    }
    base.update(over)
    return base


def test_parse_sorts_units_and_edges() -> None:
    m = make_model([unit("b.y"), unit("a.x")], [("b.y", "a.x", 2)])
    assert [u.id for u in m.units] == ["a.x", "b.y"]
    assert m.edges == (core.Edge("b.y", "a.x", 2),)
    assert m.units[0].group == "a" and m.units[0].layer_hint is None


def test_optional_unit_fields_default() -> None:
    raw = _raw(units=[{"id": "a.x", "path": "a/x.py", "group": "a", "loc": 3}])
    u = core.parse_model(raw).units[0]
    assert (u.layer_hint, u.types, u.escapes, u.framework_refs) == (None, (), {}, ())


def test_wrong_schema_raises() -> None:
    with pytest.raises(core.ModelError, match=r"domain-powers\.assess\.model/1"):
        core.parse_model(_raw(schema="domain-powers.assess.model/2"))


def test_edge_to_unknown_unit_raises() -> None:
    with pytest.raises(core.ModelError, match=r"a\.ghost"):
        make_model([unit("a.x")], [("a.x", "a.ghost", 1)])


def test_duplicate_unit_id_raises() -> None:
    with pytest.raises(core.ModelError, match=r"a\.x"):
        make_model([unit("a.x"), unit("a.x")])


def test_non_object_json_raises(tmp_path: Path) -> None:
    f = tmp_path / "m.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(core.ModelError):
        core.load_model(f)


def test_load_model_unreadable_and_bad_json(tmp_path: Path) -> None:
    with pytest.raises(core.ModelError):
        core.load_model(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(core.ModelError):
        core.load_model(bad)


def test_load_model_round_trip(tmp_path: Path) -> None:
    f = tmp_path / "m.json"
    f.write_text(json.dumps(_raw(units=[unit("a.x")])), encoding="utf-8")
    assert core.load_model(f).units[0].id == "a.x"


def test_require_records_first_missing_capability() -> None:
    m = make_model([unit("a.x")], capabilities=["types"])
    na: core.NotApplicable = {}
    assert not core.require(m, na, "unit_cycles", "edges")
    assert na == {"unit_cycles": "missing capability: edges"}
    assert core.require(m, na, "terms", "types")
