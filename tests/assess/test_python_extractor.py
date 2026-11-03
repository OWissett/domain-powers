"""Tests for the Python extractor: units, groups, hints and edges."""

import json
import sys
from pathlib import Path

import pytest
from extractors import python as pyx
from helpers import write_tree

ALL_CAPABILITIES = ["data_only", "edges", "escapes", "framework_refs", "layer_hints", "types"]


def units_by_id(model: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = model["units"]
    assert isinstance(raw, list)
    out: dict[str, dict[str, object]] = {}
    for item in raw:
        assert isinstance(item, dict)
        out[str(item["id"])] = item
    return out


def test_ids_paths_and_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "src",
        {
            "shop/__init__.py": "",
            "shop/cli.py": "x = 1\n",
            "shop/models/__init__.py": "",
            "shop/models/order.py": "y = 2\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    model = pyx.extract(Path("src"))
    units = units_by_id(model)
    assert sorted(units) == ["shop", "shop.cli", "shop.models", "shop.models.order"]
    assert units["shop.models.order"]["group"] == "shop.models"
    assert units["shop.models.order"]["path"] == "src/shop/models/order.py"
    assert units["shop.cli"]["group"] == "shop"
    assert units["shop.models"]["group"] == "shop.models"
    assert units["shop"]["group"] == "shop"
    assert model["root"] == "src"
    assert model["schema"] == "domain-powers.assess.model/1"
    assert model["language"] == "python"


def test_no_root_package_groups_by_first_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_tree(tmp_path / "src", {"a/x.py": "", "b/y.py": ""})
    monkeypatch.chdir(tmp_path)
    units = units_by_id(pyx.extract(Path("src")))
    assert units["a.x"]["group"] == "a"
    assert units["b.y"]["group"] == "b"


def test_explicit_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "src", {"a/x.py": "", "b/y/z.py": ""})
    monkeypatch.chdir(tmp_path)
    units = units_by_id(pyx.extract(Path("src"), package="b"))
    assert units["b.y.z"]["group"] == "b.y"
    assert units["a.x"]["group"] == "a"


def test_loc_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    write_tree(tmp_path / "src", {"m.py": "x = 1\n\n# c\n  # d\ny = 2\n"})
    assert units_by_id(pyx.extract(tmp_path / "src"))["m"]["loc"] == 2


@pytest.mark.parametrize(
    ("rel", "hint"),
    [
        ("shop/models/order.py", "models"),
        ("shop/repos/x.py", "repositories"),
        ("shop/billing/views.py", "views"),
        ("shop/ordering/thing.py", None),
        ("shop/models/__init__.py", "models"),
    ],
)
def test_layer_hints(tmp_path: Path, rel: str, hint: str | None) -> None:
    write_tree(tmp_path / "src", {rel: "", "shop/other.py": ""})
    units = units_by_id(pyx.extract(tmp_path / "src"))
    module = rel.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
    assert units[module]["layer_hint"] == hint


def test_edges_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "src",
        {
            "shop/models/__init__.py": "",
            "shop/models/order.py": "",
            "shop/services/a.py": (
                "import shop.models.order\n"
                "from ..models import order\n"
                "from shop.models import Thing\n"
                "import shop.models.order.missing\n"
                "import json\n"
            ),
        },
    )
    monkeypatch.chdir(tmp_path)
    assert pyx.extract(Path("src"))["edges"] == [
        {"from": "shop.services.a", "to": "shop.models", "count": 1},
        {"from": "shop.services.a", "to": "shop.models.order", "count": 3},
    ]


def test_self_edges_are_dropped(tmp_path: Path) -> None:
    write_tree(tmp_path / "src", {"shop/a.py": "import shop.a\n", "shop/b.py": ""})
    assert pyx.extract(tmp_path / "src")["edges"] == []


def test_namespace_packages_without_init(tmp_path: Path) -> None:
    write_tree(
        tmp_path / "src",
        {"shop/models/order.py": "", "shop/services/a.py": "from shop.models import order\n"},
    )
    model = pyx.extract(tmp_path / "src")
    assert sorted(units_by_id(model)) == ["shop.models.order", "shop.services.a"]
    assert model["edges"] == [{"from": "shop.services.a", "to": "shop.models.order", "count": 1}]


@pytest.mark.parametrize(
    "rel", ["tests/test_x.py", "shop/test_y.py", "shop/y_test.py", "shop/conftest.py"]
)
def test_tests_excluded_by_default_and_included_with_flag(tmp_path: Path, rel: str) -> None:
    write_tree(tmp_path / "src", {"shop/a.py": "import tests.test_x\n", rel: "import shop.a\n"})
    module = rel.removesuffix(".py").replace("/", ".")
    default = pyx.extract(tmp_path / "src")
    assert module not in units_by_id(default)
    assert default["edges"] == []
    included = pyx.extract(tmp_path / "src", include_tests=True)
    assert units_by_id(included)[module]["layer_hint"] == "tests"


def test_exclude_glob(tmp_path: Path) -> None:
    write_tree(
        tmp_path / "src",
        {
            "shop/a.py": "from shop.generated import g\n",
            "shop/generated/g.py": "import shop.a\n",
            "shop/b.py": "import shop.a\n",
        },
    )
    model = pyx.extract(tmp_path / "src", exclude=["shop/generated/*"])
    assert sorted(units_by_id(model)) == ["shop.a", "shop.b"]
    assert model["edges"] == [{"from": "shop.b", "to": "shop.a", "count": 1}]


def test_syntax_error_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "src", {"shop/ok.py": "x = 1\n", "shop/bad.py": "def (:\n"})
    monkeypatch.chdir(tmp_path)
    model = pyx.extract(Path("src"))
    assert model["skipped"] == [{"path": "src/shop/bad.py", "reason": "syntax error"}]
    assert sorted(units_by_id(model)) == ["shop.ok"]


def test_non_utf8_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "src", {"shop/ok.py": "x = 1\n"})
    (tmp_path / "src" / "shop" / "bad.py").write_bytes(b"\xff\xfe x = 1")
    monkeypatch.chdir(tmp_path)
    model = pyx.extract(Path("src"))
    assert model["skipped"] == [{"path": "src/shop/bad.py", "reason": "not UTF-8"}]
    out = tmp_path / "m.json"
    assert pyx.main([str(tmp_path / "src"), "--out", str(out)]) == 0


def test_skips_environment_and_hidden_dirs(tmp_path: Path) -> None:
    files = {"shop/real.py": ""}
    for name in (".venv", "venv", "build", "dist", "node_modules", ".tox", "x.egg-info"):
        files[f"{name}/lib/mod.py"] = ""
    files["site-packages/pkg/mod.py"] = ""
    files["custom_env/pyvenv.cfg"] = ""
    files["custom_env/lib/mod.py"] = ""
    files["shop/__pycache__/cached.py"] = ""
    write_tree(tmp_path / "src", files)
    assert sorted(units_by_id(pyx.extract(tmp_path / "src"))) == ["shop.real"]


def test_capabilities_declared(tmp_path: Path) -> None:
    write_tree(tmp_path / "src", {"shop/a.py": ""})
    assert tuple(ALL_CAPABILITIES) == pyx.CAPABILITIES_DECLARED
    assert pyx.extract(tmp_path / "src")["capabilities"] == ALL_CAPABILITIES


def test_output_is_byte_identical_across_runs(tmp_path: Path) -> None:
    write_tree(
        tmp_path / "src",
        {"shop/a.py": "import shop.b\n", "shop/b.py": "import shop.a\n", "shop/c/d.py": ""},
    )
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    assert pyx.main([str(tmp_path / "src"), "--out", str(first)]) == 0
    assert pyx.main([str(tmp_path / "src"), "--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8").endswith("}\n")


def test_cli_exit_codes(tmp_path: Path) -> None:
    write_tree(tmp_path / "src", {"shop/a.py": ""})
    out = tmp_path / "m.json"
    assert pyx.main([str(tmp_path / "missing"), "--out", str(out)]) == 2
    assert pyx.main([str(tmp_path / "src"), "--out", str(out), "--package", "nope"]) == 2
    assert pyx.main([str(tmp_path / "src")]) == 2
    assert pyx.main([str(tmp_path / "src"), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == "domain-powers.assess.model/1"


def test_script_runs_as_a_command(tmp_path: Path) -> None:
    import subprocess

    write_tree(tmp_path / "src", {"shop/a.py": ""})
    script = Path(pyx.__file__)
    out = tmp_path / "m.json"
    done = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "src"), "--out", str(out)],
        check=False,
        capture_output=True,
    )
    assert done.returncode == 0
    assert out.exists()


def one_unit(model: dict[str, object], unit_id: str) -> dict[str, object]:
    return units_by_id(model)[unit_id]


def test_data_only_rules(tmp_path: Path) -> None:
    source = (
        "from dataclasses import dataclass\n"
        "from functools import cached_property\n"
        "\n"
        "@dataclass\n"
        "class A:\n"
        "    x: int\n"
        '    y: str = ""\n'
        "\n"
        "class B:\n"
        '    """Doc."""\n'
        "    @property\n"
        "    def n(self) -> int:\n"
        "        return 1\n"
        "    @n.setter\n"
        "    def n(self, v: int) -> None:\n"
        "        pass\n"
        "    @cached_property\n"
        "    def m(self) -> int:\n"
        "        return 2\n"
        "    def __eq__(self, other: object) -> bool:\n"
        "        return True\n"
        "\n"
        "class C(Model):\n"
        "    name = Column()\n"
        "    class Meta:\n"
        "        table = 'c'\n"
        "\n"
        "class D:\n"
        "    def total(self) -> int:\n"
        "        return 1\n"
        "\n"
        "def f() -> None:\n"
        "    class Inner:\n"
        "        ...\n"
    )
    write_tree(tmp_path, {"m.py": source})
    unit = one_unit(pyx.extract(tmp_path), "m")
    assert unit["types"] == [
        {"name": "A", "data_only": True},
        {"name": "B", "data_only": True},
        {"name": "C", "data_only": True},
        {"name": "D", "data_only": False},
    ]


def test_escape_kinds(tmp_path: Path) -> None:
    source = (
        "from typing import Any, cast\n"
        "def f(x: Any) -> None:\n"
        "    y = cast(int, x)  # type: ignore[misc]\n"
        "def g(z):\n"
        "    return z\n"
    )
    write_tree(tmp_path, {"m.py": source, "clean.py": "x: int = 1\n"})
    units = units_by_id(pyx.extract(tmp_path))
    assert units["m"]["escapes"] == {"ANY": 2, "CAST": 1, "IGNORE": 1, "UNTYPED": 1}
    assert units["clean"]["escapes"] == {}


def test_allow_justification_outside_domain_only(tmp_path: Path) -> None:
    source = "from typing import Any\nx: Any = 1  # domain-powers: allow legacy\n"
    write_tree(
        tmp_path,
        {
            "shop/web/a.py": source,
            "shop/billing/domain/a.py": source,
        },
    )
    units = units_by_id(pyx.extract(tmp_path))
    assert units["shop.web.a"]["escapes"] == {"ANY": 1}
    assert units["shop.billing.domain.a"]["escapes"] == {"ANY": 2}


def test_tests_units_count_only_ignore(tmp_path: Path) -> None:
    source = "from typing import Any\ndef test_x(a):\n    b: Any = a  # type: ignore[assignment]\n"
    write_tree(tmp_path, {"shop/tests/test_a.py": source, "shop/b.py": "x = 1\n"})
    units = units_by_id(pyx.extract(tmp_path, include_tests=True))
    assert units["shop.tests.test_a"]["escapes"] == {"IGNORE": 1}


def test_framework_refs(tmp_path: Path) -> None:
    source = (
        "import sqlalchemy.orm\nfrom flask import Flask\n"
        "import os\nfrom . import x\nimport shop.y\n"
    )
    write_tree(tmp_path, {"shop/a.py": source, "shop/x.py": "", "shop/y.py": ""})
    unit = one_unit(pyx.extract(tmp_path), "shop.a")
    assert unit["framework_refs"] == ["flask", "os", "sqlalchemy"]
