import json
import subprocess
import sys
from pathlib import Path

from helpers import write_tree
from legacy import LEGACY_TREE, SLICE_TREE, TARGET_TOML

TOOLS = Path(__file__).resolve().parents[2] / "skills" / "assessing-domain-migration" / "tools"


def _run(cwd: Path, tool: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), *args], cwd=cwd, capture_output=True, text=True
    )


def extract(cwd: Path, tree: dict[str, str], model: str = "model.json") -> Path:
    write_tree(cwd / "src", tree)
    done = _run(cwd, TOOLS / "extractors" / "python.py", "src", "--out", model)
    assert done.returncode == 0, done.stderr
    return cwd / model


def analyse(cwd: Path, tree: dict[str, str], *, target: bool, out: str = "out") -> Path:
    model = extract(cwd, tree)
    args = [str(model), "--out-dir", out]
    if target:
        (cwd / "target.toml").write_text(TARGET_TOML, encoding="utf-8")
        args += ["--target", "target.toml"]
    done = _run(cwd, TOOLS / "core.py", "analyse", *args)
    assert done.returncode == 0, done.stderr
    return cwd / out / "assessment.json"


def as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {str(k): v for k, v in value.items()}


def as_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return list(value)


def load(path: Path) -> dict[str, object]:
    return as_dict(json.loads(path.read_text(encoding="utf-8")))


def run_analyse(cwd: Path, tree: dict[str, str], *, target: bool) -> dict[str, object]:
    return load(analyse(cwd, tree, target=target))


def test_legacy_assessment(tmp_path: Path) -> None:
    a = run_analyse(tmp_path, LEGACY_TREE, target=True)
    assert a["layout"] == "technical layering"
    assert a["unit_cycles"] == [["shop.models.base", "shop.utils.money"]]
    assert a["group_cycles"] == [["shop.models", "shop.utils"]]
    assert as_list(a["hubs"])[0] == {"id": "shop.models.base", "fan_in": 4}
    terms = as_dict(a["terms"])
    scattered = [as_dict(s)["term"] for s in as_list(terms["scattered"])]
    assert scattered == ["invoice", "order"] and terms["distinct"] == 4
    clusters = {
        as_dict(c)["name"]: as_dict(c)["members"]
        for c in as_list(as_dict(a["clusters"])["clusters"])
    }
    assert clusters["order-line"] == [
        "shop.models.order",
        "shop.services.checkout",
        "shop.views.orders",
    ]
    assert clusters["invoice-line"] == [
        "shop.models.invoice",
        "shop.services.billing",
        "shop.views.invoices",
    ]
    assert clusters["money"] == ["shop.models.base", "shop.utils.money"]
    distance = as_dict(a["distance"])
    assert distance["unassigned"] == ["shop.models.base", "shop.utils.money"]
    assert distance["pairs"] == [
        {"source": "billing", "target": "ordering", "via_public": 1, "into_internals": 1}
    ]
    assert a["scorecard"] == {
        "boundaries": 3,
        "language": 0,
        "model_richness": 0,
        "framework_isolation": 1,
        "type_safety": 0,
    }
    assert a["ratchet"] == {
        "unit_cycle_members": 2,
        "edges_into_internals": 1,
        "escapes": 3,
        "framework_refs_non_generic": 4,
        "unassigned_units": 2,
    }


def test_legacy_without_target(tmp_path: Path) -> None:
    a = run_analyse(tmp_path, LEGACY_TREE, target=False)
    card = as_dict(a["scorecard"])
    assert card["boundaries"] == 1 and card["framework_isolation"] == 0


def test_extraction_is_reproducible(tmp_path: Path) -> None:
    write_tree(tmp_path / "src", LEGACY_TREE)
    tool = TOOLS / "extractors" / "python.py"
    for name in ("a.json", "b.json"):
        assert _run(tmp_path, tool, "src", "--out", name).returncode == 0
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def compare(cwd: Path, baseline: Path, current: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        cwd, TOOLS / "core.py", "compare", "--baseline", str(baseline), "--current", str(current)
    )


def status_of(report: str, metric: str) -> str:
    for line in report.splitlines():
        cells = line.split()
        if cells[:1] == [metric]:
            return cells[-1]
    raise AssertionError(f"no row {metric}")


def test_slice_passes_then_regression_fails(tmp_path: Path) -> None:
    legacy_dir, slice_dir, bad_dir = (tmp_path / n for n in ("legacy", "slice", "bad"))
    for d in (legacy_dir, slice_dir, bad_dir):
        d.mkdir()
    legacy = analyse(legacy_dir, LEGACY_TREE, target=True)
    sliced = analyse(slice_dir, SLICE_TREE, target=True)
    ok = compare(tmp_path, legacy, sliced)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert status_of(ok.stdout, "edges_into_internals") == "progress"
    regressed = dict(SLICE_TREE)
    regressed["shop/billing/api.py"] = (
        "from shop.models.order import Order\n" + SLICE_TREE["shop/billing/api.py"]
    )
    bad = analyse(bad_dir, regressed, target=True)
    fail = compare(tmp_path, sliced, bad)
    assert fail.returncode == 1, fail.stdout + fail.stderr
    assert status_of(fail.stdout, "edges_into_internals") == "INCREASED"
