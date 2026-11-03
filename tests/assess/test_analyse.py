import json
from pathlib import Path

import core
import pytest
from helpers import make_model, unit

HEADINGS = [
    "# Migration assessment",
    "## Summary",
    "## Scorecard",
    "## Recommendation",
    "## Layout",
    "## Cycles",
    "## Hubs",
    "## Churn",
    "## Scattered terms",
    "## Candidate contexts",
    "## Hotspot findings",
    "## Contexts",
    "## Distance to target",
    "## Work list",
    "## Slices",
]
FIELDS = {
    "language", "capabilities", "not_applicable", "summary", "layout", "unit_cycles",
    "group_cycles", "hubs", "coupling", "churn", "terms", "richness", "framework",
    "escapes", "clusters", "target", "distance", "scorecard", "ratchet",
}  # fmt: skip


def raw_model(*, reverse: bool = False, capabilities: list[str] | None = None) -> dict[str, object]:
    units = [
        unit("shop.models.order", hint="models", types=[("Order", False)], escapes={"any": 2}),
        unit("shop.services.checkout", hint="services", types=[("Checkout", False)]),
        unit("shop.billing.invoice", hint="models", types=[("Invoice", True)], refs=["orm"]),
    ]
    edges = [
        {"from": "shop.services.checkout", "to": "shop.models.order", "count": 3},
        {"from": "shop.services.checkout", "to": "shop.billing.invoice", "count": 1},
        {"from": "shop.billing.invoice", "to": "shop.services.checkout", "count": 2},
    ]
    if reverse:
        units.reverse()
        edges.reverse()
    caps = sorted(core.CAPABILITIES) if capabilities is None else capabilities
    return {
        "schema": core.MODEL_SCHEMA,
        "language": "python",
        "root": "src",
        "capabilities": caps,
        "units": units,
        "edges": edges,
        "skipped": [],
    }


def write(tmp_path: Path, name: str, raw: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


TARGET = """
[contexts.ordering]
classification = "core"
units = ["shop.models.order*", "shop.services.checkout*"]
public = ["shop.services.checkout"]

[contexts.billing]
classification = "supporting"
units = ["shop.billing.*"]
public = []
"""


@pytest.mark.parametrize("dim", sorted(core.BOUNDS))
@pytest.mark.parametrize("i", range(5))
def test_score_at_every_bound(dim: str, i: int) -> None:
    b = core.BOUNDS[dim]
    assert core.score(b[i], b) == 5 - i
    assert core.score(b[i] + 1e-9, b) == 4 - i


def test_score_none() -> None:
    assert core.score(None, core.BOUNDS["language"]) is None


def test_boundaries_capped_without_target() -> None:
    model = make_model([unit("a.x"), unit("b.x")], [("a.x", "b.x", 1)])
    a = core.assess(model, None, None)
    assert a.group_cycles == []
    assert a.scorecard.boundaries == 4


def test_boundaries_with_group_cycle_without_target() -> None:
    model = make_model([unit("a.x"), unit("b.x")], [("a.x", "b.x", 1), ("b.x", "a.x", 1)])
    assert core.assess(model, None, None).scorecard.boundaries == 0


def test_ratchet_without_target() -> None:
    model = make_model([unit("a.x", escapes={"any": 2}), unit("b.x")], [("a.x", "b.x", 1)])
    r = core.assess(model, None, None).ratchet
    assert r == core.Ratchet(0, None, 2, None, None)


def test_ratchet_with_target(tmp_path: Path) -> None:
    model = core.parse_model(raw_model())
    target = core.parse_target(TARGET)
    a = core.assess(model, target, None)
    # checkout -> invoice (1, into internals), invoice -> checkout is public
    assert a.ratchet.edges_into_internals == 1
    assert a.ratchet.unassigned_units == 0
    assert a.ratchet.framework_refs_non_generic == 1
    assert a.ratchet.unit_cycle_members == 2
    assert a.scorecard.boundaries == core.score(1 / 6, core.BOUNDS["boundaries"])


def test_assessment_json_keys() -> None:
    a = core.assess(core.parse_model(raw_model()), core.parse_target(TARGET), None)
    out = core.assessment_json(a)
    assert set(out) == {"schema"} | FIELDS
    assert out["schema"] == core.RESULT_SCHEMA
    hubs = out["hubs"]
    assert isinstance(hubs, list) and hubs[0] == {"id": "shop.billing.invoice", "fan_in": 1}
    assert out["scorecard"] == {
        "boundaries": a.scorecard.boundaries,
        "language": a.scorecard.language,
        "model_richness": a.scorecard.model_richness,
        "framework_isolation": a.scorecard.framework_isolation,
        "type_safety": a.scorecard.type_safety,
    }
    assert isinstance(out["ratchet"], dict)
    assert set(out["ratchet"]) == {
        "unit_cycle_members", "edges_into_internals", "escapes",
        "framework_refs_non_generic", "unassigned_units",
    }  # fmt: skip
    distance = out["distance"]
    assert isinstance(distance, dict)
    pairs = distance["pairs"]
    assert isinstance(pairs, list)
    first = pairs[0]
    assert isinstance(first, dict)
    assert set(first) == {"source", "target", "via_public", "into_internals"}
    assert out["capabilities"] == sorted(core.CAPABILITIES)


def test_analyse_writes_both_files(tmp_path: Path) -> None:
    model = write(tmp_path, "model.json", raw_model())
    out = tmp_path / "out" / "nested"
    assert core.main(["analyse", str(model), "--out-dir", str(out)]) == 0
    md = (out / "assessment.md").read_text(encoding="utf-8")
    positions = [md.index(h + "\n") for h in HEADINGS]
    assert positions == sorted(positions)
    assert md.count(core.HUMAN_PLACEHOLDER) == 4
    assert json.loads((out / "assessment.json").read_text(encoding="utf-8"))["schema"] == (
        core.RESULT_SCHEMA
    )


def test_analyse_with_target(tmp_path: Path) -> None:
    model = write(tmp_path, "model.json", raw_model())
    target = tmp_path / "target.toml"
    target.write_text(TARGET, encoding="utf-8")
    out = tmp_path / "out"
    assert core.main(["analyse", str(model), "--out-dir", str(out), "--target", str(target)]) == 0
    md = (out / "assessment.md").read_text(encoding="utf-8")
    assert "shop.billing.invoice" in md.split("## Work list")[1]


def test_analyse_is_deterministic(tmp_path: Path) -> None:
    outs = []
    for i, rev in enumerate((False, True)):
        model = write(tmp_path, f"m{i}.json", raw_model(reverse=rev))
        out = tmp_path / f"out{i}"
        assert core.main(["analyse", str(model), "--out-dir", str(out)]) == 0
        outs.append(out)
    for name in ("assessment.json", "assessment.md"):
        assert (outs[0] / name).read_bytes() == (outs[1] / name).read_bytes()


def test_analyse_overlap_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = write(tmp_path, "model.json", raw_model())
    target = tmp_path / "target.toml"
    target.write_text(
        '[contexts.a]\nclassification = "core"\nunits = ["shop.models.*"]\n'
        '[contexts.b]\nclassification = "core"\nunits = ["shop.models.order"]\n',
        encoding="utf-8",
    )
    code = core.main(
        ["analyse", str(model), "--out-dir", str(tmp_path / "o"), "--target", str(target)]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "shop.models.order" in err and "a" in err and "b" in err


def test_analyse_bad_schema_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = write(tmp_path, "model.json", {"schema": "nope"})
    assert core.main(["analyse", str(model), "--out-dir", str(tmp_path / "o")]) == 2
    assert capsys.readouterr().err


def test_markdown_marks_not_applicable(tmp_path: Path) -> None:
    caps = sorted(core.CAPABILITIES - {"edges"})
    model = write(tmp_path, "model.json", raw_model(capabilities=caps))
    out = tmp_path / "out"
    assert core.main(["analyse", str(model), "--out-dir", str(out)]) == 0
    md = (out / "assessment.md").read_text(encoding="utf-8")
    assert "n/a: missing capability: edges" in md
    assert "Missing capabilities: edges" in md


def test_markdown_reports_no_separable_clusters() -> None:
    a = core.assess(make_model([unit("a.x", types=[("Order", False)])]), None, None)
    assert a.clusters is not None and not a.clusters.separable
    assert "No separable clusters found." in core.render_markdown(a)


def test_analyse_overlap_exits_2_without_edges_or_framework_refs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = write(tmp_path, "model.json", raw_model(capabilities=["types"]))
    target = tmp_path / "target.toml"
    target.write_text(
        '[contexts.a]\nclassification = "core"\nunits = ["shop.models.*"]\n'
        '[contexts.b]\nclassification = "core"\nunits = ["shop.models.order"]\n',
        encoding="utf-8",
    )
    argv = ["analyse", str(model), "--out-dir", str(tmp_path / "o"), "--target", str(target)]
    assert core.main(argv) == 2
    assert "shop.models.order" in capsys.readouterr().err
