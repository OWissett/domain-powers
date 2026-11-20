"""Tests for the Rust extractor: units, groups, edges, types, escapes and the core round trip."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import core
import pytest
from extractors import rust as rsx
from helpers import write_tree

EXTRACTOR = Path(__file__).resolve().parents[2] / "scripts" / "assess" / "extractors" / "rust.py"


def units_by_id(model: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = model["units"]
    assert isinstance(raw, list)
    return {str(u["id"]): u for u in raw if isinstance(u, dict)}


def edges(model: dict[str, object]) -> dict[tuple[str, str], int]:
    raw = model["edges"]
    assert isinstance(raw, list)
    return {(str(e["from"]), str(e["to"])): int(e["count"]) for e in raw if isinstance(e, dict)}


SINGLE = {
    "Cargo.toml": '[package]\nname = "shop"\nversion = "0.1.0"\n',
    "src/lib.rs": "pub mod ordering;\npub mod util;\n",
    "src/util.rs": "pub fn helper() {}\n",
    "src/ordering.rs": "pub mod order;\npub mod service;\n",
    "src/ordering/order.rs": "pub struct Order { pub id: u32 }\n",
    "src/ordering/service.rs": (
        "use crate::ordering::order::Order;\n"
        "use super::order;\n"
        "pub fn run() { crate::util::helper(); let _ = order::Order { id: 1 }; }\n"
    ),
}


def test_ids_and_groups_single_crate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "shop", SINGLE)
    monkeypatch.chdir(tmp_path)
    model = rsx.extract(Path("shop"))
    units = units_by_id(model)
    assert sorted(units) == [
        "shop",
        "shop::ordering",
        "shop::ordering::order",
        "shop::ordering::service",
        "shop::util",
    ]
    assert units["shop::ordering::order"]["group"] == "shop::ordering"
    assert units["shop::ordering"]["group"] == "shop::ordering"
    assert units["shop::util"]["group"] == "shop"
    assert units["shop::ordering::order"]["path"] == "shop/src/ordering/order.rs"
    assert model["language"] == "rust"
    assert model["schema"] == "domain-powers.assess.model/1"
    assert model["root"] == "shop"


def test_edges_from_use_and_qualified_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_tree(tmp_path / "shop", SINGLE)
    monkeypatch.chdir(tmp_path)
    found = edges(rsx.extract(Path("shop")))
    assert found[("shop::ordering::service", "shop::ordering::order")] == 2
    assert found[("shop::ordering::service", "shop::util")] == 1
    assert ("shop", "shop::ordering") not in found  # `mod` declarations are structure


def test_groups_by_crate_in_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "ws",
        {
            "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n',
            "crates/ordering/Cargo.toml": '[package]\nname = "ordering"\nversion = "0.1.0"\n',
            "crates/ordering/src/lib.rs": "pub mod api;\nmod domain;\n",
            "crates/ordering/src/api.rs": "use billing::api::Charge;\n",
            "crates/ordering/src/domain/mod.rs": "pub mod order;\n",
            "crates/ordering/src/domain/order.rs": "pub struct Order;\n",
            "crates/billing/Cargo.toml": '[package]\nname = "billing"\nversion = "0.1.0"\n',
            "crates/billing/src/lib.rs": "pub mod api;\n",
            "crates/billing/src/api.rs": "pub struct Charge;\n",
            "target/debug/build/x/out/gen.rs": "pub struct Generated;\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    model = rsx.extract(Path("ws"))
    units = units_by_id(model)
    assert sorted(units) == [
        "billing",
        "billing::api",
        "ordering",
        "ordering::api",
        "ordering::domain",
        "ordering::domain::order",
    ]
    assert units["ordering::domain::order"]["group"] == "ordering"
    assert units["ordering::domain::order"]["layer_hint"] == "domain"
    assert units["ordering::api"]["layer_hint"] == "api"
    assert edges(model) == {("ordering::api", "billing::api"): 1}


def test_package_option_groups_one_crate_by_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_tree(
        tmp_path / "ws",
        {
            "a/Cargo.toml": '[package]\nname = "a"\nversion = "0.1.0"\n',
            "a/src/lib.rs": "",
            "a/src/x/mod.rs": "",
            "b/Cargo.toml": '[package]\nname = "b-crate"\nversion = "0.1.0"\n',
            "b/src/lib.rs": "",
        },
    )
    monkeypatch.chdir(tmp_path)
    units = units_by_id(rsx.extract(Path("ws"), package="a"))
    assert units["a::x"]["group"] == "a::x"
    assert units["b_crate"]["group"] == "b_crate"


def test_types_and_data_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "shop",
        {
            "Cargo.toml": '[package]\nname = "shop"\nversion = "0.1.0"\n',
            "src/lib.rs": (
                "pub struct Plain { a: u32 }\n"
                "pub struct Accessed { a: u32, b: String }\n"
                "impl<T: Into<String>> Accessed {\n"
                "    pub fn new(a: u32) -> Self { Self { a, b: String::new() } }\n"
                "    pub fn a(&self) -> u32 { self.a }\n"
                "    pub fn b(&self) -> &String { &self.b }\n"
                "}\n"
                "impl std::fmt::Display for Accessed {\n"
                "    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { todo!() }\n"
                "}\n"
                "pub enum State { Draft, Placed }\n"
                "pub struct Rich { total: u32 }\n"
                "impl Rich {\n"
                "    pub fn add(&mut self, n: u32) { self.total += n; }\n"
                "}\n"
                "pub trait Repo { fn get(&self) -> u32; }\n"
                "fn f() { struct Inner; }\n"
                "#[cfg(test)]\nmod tests { struct Fixture; }\n"
            ),
        },
    )
    monkeypatch.chdir(tmp_path)
    units = units_by_id(rsx.extract(Path("shop")))
    assert units["shop"]["types"] == [
        {"name": "Plain", "data_only": True},
        {"name": "Accessed", "data_only": True},
        {"name": "State", "data_only": True},
        {"name": "Rich", "data_only": False},
        {"name": "Repo", "data_only": False},
    ]


def test_escapes_and_framework_refs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "shop",
        {
            "Cargo.toml": '[package]\nname = "shop"\nversion = "0.1.0"\n',
            "src/lib.rs": "pub mod domain;\npub mod infra;\n",
            "src/domain.rs": (
                "use serde::Deserialize;\n"
                "pub fn f(x: Option<u8>) -> u8 { x.unwrap() }\n"
                "pub fn g() { a.unwrap(); } // domain-powers: allow rejected in domain\n"
            ),
            "src/infra.rs": (
                "use sqlx::PgPool;\n"
                'pub fn h() { std::fs::read("x"); unsafe { } }\n'
                "pub fn i() { a.unwrap(); } // domain-powers: allow startup only\n"
                "#[allow(dead_code)]\nfn j() {}\n"
            ),
        },
    )
    monkeypatch.chdir(tmp_path)
    units = units_by_id(rsx.extract(Path("shop")))
    assert units["shop::domain"]["escapes"] == {"PANIC": 2}
    assert units["shop::domain"]["framework_refs"] == ["serde"]
    assert units["shop::infra"]["escapes"] == {"IGNORE": 1, "UNSAFE": 1}
    assert units["shop::infra"]["framework_refs"] == ["sqlx", "std::fs"]


def test_tests_excluded_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "shop",
        {
            "Cargo.toml": '[package]\nname = "shop"\nversion = "0.1.0"\n',
            "src/lib.rs": "",
            "tests/order.rs": "use shop::Order;\n",
            "benches/b.rs": "",
        },
    )
    monkeypatch.chdir(tmp_path)
    assert sorted(units_by_id(rsx.extract(Path("shop")))) == ["shop"]
    with_tests = units_by_id(rsx.extract(Path("shop"), include_tests=True))
    assert with_tests["shop::tests::order"]["layer_hint"] == "tests"


def test_exclude_glob(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "shop", {**SINGLE, "src/generated/proto.rs": "pub struct P;\n"})
    monkeypatch.chdir(tmp_path)
    units = units_by_id(rsx.extract(Path("shop"), exclude=["src/generated/*"]))
    assert "shop::generated::proto" not in units


def test_deterministic_output_and_cli(tmp_path: Path) -> None:
    write_tree(tmp_path / "shop", SINGLE)
    outs = []
    for name in ("a.json", "b.json"):
        done = subprocess.run(
            [sys.executable, str(EXTRACTOR), "shop", "--out", name],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        outs.append((tmp_path / name).read_bytes())
    assert outs[0] == outs[1]
    bad = subprocess.run(
        [sys.executable, str(EXTRACTOR), "missing", "--out", "x.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2


def test_model_accepted_by_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(tmp_path / "shop", SINGLE)
    monkeypatch.chdir(tmp_path)
    model = core.parse_model(json.loads(json.dumps(rsx.extract(Path("shop")))))
    result = core.assess(model, None, None)
    assert result.language == "rust"
    assert not result.not_applicable.get("hubs")


def test_escape_counts_match_the_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_tree(
        tmp_path / "shop",
        {
            "Cargo.toml": '[package]\nname = "shop"\nversion = "0.1.0"\n',
            "src/lib.rs": "pub fn f() { a.unwrap(); b.unwrap(); }\npub fn g() { c.unwrap(); }\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    assert units_by_id(rsx.extract(Path("shop")))["shop"]["escapes"] == {"PANIC": 2}
