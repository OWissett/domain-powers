import shutil
import subprocess
from pathlib import Path

import core
import pytest
from helpers import make_model, unit


def test_strongly_connected_finds_cycles() -> None:
    edges = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "e"), ("e", "c"), ("e", "f")]
    assert core.strongly_connected(list("fedcba"), edges) == [["a", "b"], ["c", "d", "e"]]


def test_strongly_connected_is_iterative() -> None:
    n = 5000
    nodes = [f"n{i}" for i in range(n)]
    edges = [(nodes[i], nodes[(i + 1) % n]) for i in range(n)]
    result = core.strongly_connected(nodes, edges)
    assert len(result) == 1 and len(result[0]) == n


def test_layout_technical_layering() -> None:
    m = make_model(
        [
            unit("a.m", hint="models"),
            unit("b.s", hint="services"),
            unit("c.v", hint="views"),
            unit("d.u", hint="utils"),
        ]
    )
    assert core.layout_style(m, {}) == "technical layering"


def test_layout_feature_packages() -> None:
    units = [
        unit(f"shop.{g}.{h}", group=f"shop.{g}", hint=h)
        for g in ("orders", "billing")
        for h in ("models", "services", "views")
    ]
    assert core.layout_style(make_model(units), {}) == "feature packages"


def test_layout_mixed() -> None:
    m = make_model([unit("a.x"), unit("b.y"), unit("c.z"), unit("d.w", hint="models")])
    assert core.layout_style(m, {}) == "mixed"


def test_layout_not_applicable_without_hints() -> None:
    na: core.NotApplicable = {}
    m = make_model([unit("a.x")], capabilities=[])
    assert core.layout_style(m, na) is None
    assert na["layout"] == "missing capability: layer_hints"


def test_unit_and_group_cycles() -> None:
    m = make_model(
        [unit("a.x"), unit("a.y"), unit("b.z")],
        [("a.x", "a.y", 1), ("a.y", "a.x", 1), ("a.x", "b.z", 1), ("b.z", "a.y", 1)],
    )
    assert core.unit_cycles(m, {}) == [["a.x", "a.y", "b.z"]]
    assert core.group_cycles(m, {}) == [["a", "b"]]


def test_group_metrics_need_two_groups() -> None:
    na: core.NotApplicable = {}
    m = make_model([unit("a.x"), unit("a.y")], [("a.x", "a.y", 1)])
    assert core.group_cycles(m, na) is None and core.coupling(m, na) is None
    assert na["group_cycles"] == na["coupling"] == "fewer than two groups"


def test_group_metrics_need_internal_edges() -> None:
    na: core.NotApplicable = {}
    m = make_model([unit("a.x"), unit("b.y")], [])
    assert core.group_cycles(m, na) is None and core.coupling(m, na) is None
    assert na["group_cycles"] == na["coupling"] == "no internal edges"


def test_hubs_top_ten_ties_by_id() -> None:
    targets = [f"t.t{i:02d}" for i in range(12)]
    units = [unit("s.a"), unit("s.b"), *[unit(t) for t in targets]]
    edges = [("s.a", t, 1) for t in targets] + [("s.b", "t.t05", 1)]
    result = core.hubs(make_model(units, edges), {})
    assert result is not None and len(result) == 10
    assert result[0] == core.Hub("t.t05", 2)
    assert [h.id for h in result[1:]] == [f"t.t{i:02d}" for i in (0, 1, 2, 3, 4, 6, 7, 8, 9)]


def test_instability() -> None:
    m = make_model([unit("a.x"), unit("b.y"), unit("c.z")], [("a.x", "b.y", 1)])
    assert core.coupling(m, {}) == [
        core.GroupCoupling("a", 0, 1, 1.0),
        core.GroupCoupling("b", 1, 0, 0.0),
        core.GroupCoupling("c", 0, 0, None),
    ]


def test_parse_numstat() -> None:
    text = "3\t2\tsrc/a.py\n-\t-\tlogo.png\n\n1\t0\tsrc/{old => new}.py\n4\t0\tsrc/a.py\n"
    assert core.parse_numstat(text) == {"src/a.py": 9}


def test_churn_outside_git(tmp_path: Path) -> None:
    na: core.NotApplicable = {}
    assert core.churn(make_model([unit("a")]), tmp_path, na) is None
    assert na["churn"] == "not a git repository"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def _repo_with_commits(repo: Path) -> None:
    (repo / "src").mkdir()
    _git(repo, "init", "-q")
    (repo / "src" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    (repo / "src" / "a.py").write_text("x = 1\ny = 3\nz = 4\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_churn_counts_lines(tmp_path: Path) -> None:
    _repo_with_commits(tmp_path)
    m = make_model([unit("src.a"), unit("src.b")])
    assert core.churn(m, tmp_path, {}) == [core.UnitChurn("src.a", 5)]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_churn_no_matching_paths(tmp_path: Path) -> None:
    _repo_with_commits(tmp_path)
    na: core.NotApplicable = {}
    assert core.churn(make_model([unit("other.a")]), tmp_path, na) is None
    assert na["churn"] == "no git paths matched units"
