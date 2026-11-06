"""Tests for the Rust pack's guard rules, directly and through the hook."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from languages import rust

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "domain_guard.py"

WORKSPACE = """[workspace]
members = ["crates/*"]

[workspace.metadata.domain-powers]
contexts = ["ordering", "billing"]
shared = ["shared_kernel"]
"""


def crate(root: Path, name: str) -> Path:
    directory = root / "crates" / name
    (directory / "src").mkdir(parents=True, exist_ok=True)
    (directory / "Cargo.toml").write_text(f'[package]\nname = "{name}"\nversion = "0.1.0"\n')
    return directory


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    (tmp_path / "Cargo.toml").write_text(WORKSPACE)
    for name in ("ordering", "billing", "shared-kernel", "ordering-domain"):
        crate(tmp_path, name)
    return tmp_path


def check(path: Path, text: str) -> list[tuple[int, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    rust.load_config.cache_clear()
    return [(f.line, f.code) for f in rust.PACK.analyse(path, text)]


def domain_file(ws: Path) -> Path:
    return ws / "crates" / "ordering" / "src" / "domain" / "order.rs"


# ---------------------------------------------------------------- escapes


def test_unsafe(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "src" / "infrastructure" / "db.rs"
    found = check(path, "unsafe fn f() {}\nfn g() { unsafe { h() } }\n")
    assert found == [(1, "UNSAFE"), (2, "UNSAFE")]


def test_panic(ws: Path) -> None:
    found = check(
        domain_file(ws),
        'fn f() {\n  a.unwrap();\n  b.expect("x");\n  todo!();\n  c.unwrap_or(1);\n}\n',
    )
    assert found == [(2, "PANIC"), (3, "PANIC"), (4, "PANIC")]


def test_cast_and_transmute(ws: Path) -> None:
    found = check(domain_file(ws), "fn f(x: u64) -> u32 { x as u32 }\nfn g() { transmute(1) }\n")
    assert found == [(1, "CAST"), (2, "CAST")]


def test_any(ws: Path) -> None:
    found = check(
        domain_file(ws),
        "use std::any::{Any, TypeId};\nfn f(x: &dyn Any) { x.downcast_ref::<u8>(); }\n",
    )
    assert found == [(1, "ANY"), (2, "ANY")]


def test_ignore_attribute(ws: Path) -> None:
    found = check(domain_file(ws), "#[allow(dead_code)]\nfn f() {}\n#![expect(unused)]\n")
    assert found == [(1, "IGNORE"), (3, "IGNORE")]


def test_allow_comment_outside_domain(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "src" / "infrastructure" / "db.rs"
    found = check(path, "fn f() { a.unwrap(); } // domain-powers: allow startup config\n")
    assert found == []


def test_allow_comment_inside_domain_rejected(ws: Path) -> None:
    path = domain_file(ws)
    text = "fn f() { a.unwrap(); } // domain-powers: allow trust me\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    rust.load_config.cache_clear()
    findings = rust.PACK.analyse(path, text)
    assert [f.code for f in findings] == ["PANIC"]
    assert "not accepted in the domain layer" in findings[0].message


def test_cfg_test_module_reports_only_ignore(ws: Path) -> None:
    text = (
        "fn f() {}\n"
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    #[allow(unused)]\n"
        "    fn t() { a.unwrap(); x as u8; }\n"
        "}\n"
    )
    assert check(domain_file(ws), text) == [(4, "IGNORE")]


def test_tests_dir_reports_only_ignore(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "tests" / "order.rs"
    text = "use billing::domain::Payment;\n#[allow(unused)]\nfn t() { a.unwrap(); }\n"
    assert check(path, text) == [(1, "CROSS-CTX"), (2, "IGNORE")]


def test_strings_and_comments_are_not_code(ws: Path) -> None:
    text = 'fn f() -> &str { "x.unwrap() unsafe as u8" } // y.unwrap()\n'
    assert check(domain_file(ws), text) == []


# ---------------------------------------------------------------- boundaries


def test_domain_uses_sqlx_is_domain_dep(ws: Path) -> None:
    assert check(domain_file(ws), "use sqlx::PgPool;\n") == [(1, "DOMAIN-DEP")]


def test_domain_qualified_framework_path_is_domain_dep(ws: Path) -> None:
    assert check(domain_file(ws), "fn f() { serde_json::to_string(&1); }\n") == [(1, "DOMAIN-DEP")]


def test_domain_uses_std_fs_is_domain_dep(ws: Path) -> None:
    text = 'use std::fs;\nuse std::collections::BTreeMap;\nfn f() { std::env::var("X"); }\n'
    assert check(domain_file(ws), text) == [(1, "DOMAIN-DEP"), (3, "DOMAIN-DEP")]


def test_domain_glob_forbidden_crate(ws: Path) -> None:
    assert check(domain_file(ws), "use aws_sdk_s3::Client;\n") == [(1, "DOMAIN-DEP")]


def test_domain_uses_shared_kernel_and_own_domain_ok(ws: Path) -> None:
    text = (
        "use shared_kernel::Money;\nuse crate::domain::values::Sku;\nuse super::events::Placed;\n"
    )
    assert check(domain_file(ws), text) == []


def test_domain_uses_own_application_is_domain_dep(ws: Path) -> None:
    assert check(domain_file(ws), "use crate::application::PlaceOrder;\n") == [(1, "DOMAIN-DEP")]


def test_local_module_shadows_forbidden_crate(ws: Path) -> None:
    text = "mod http {\n    pub fn status() {}\n}\nfn f() { http::status(); }\n"
    assert check(domain_file(ws), text) == []


def test_application_uses_infrastructure_is_layer(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "src" / "application" / "place.rs"
    assert check(path, "use crate::infrastructure::PgOrders;\n") == [(1, "LAYER")]


def test_cross_context_internals(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "src" / "application" / "place.rs"
    assert check(path, "use billing::domain::Payment;\n") == [(1, "CROSS-CTX")]


def test_cross_context_api_ok(ws: Path) -> None:
    path = ws / "crates" / "ordering" / "src" / "application" / "place.rs"
    assert check(path, "use billing::api::PaymentRequest;\n") == []


def test_split_domain_crate(ws: Path) -> None:
    path = ws / "crates" / "ordering-domain" / "src" / "order.rs"
    assert check(path, "use crate::values::Sku;\nuse reqwest::Client;\n") == [(2, "DOMAIN-DEP")]
    other = ws / "crates" / "billing" / "src" / "application" / "x.rs"
    assert check(other, "use ordering_domain::Order;\n") == [(1, "CROSS-CTX")]


def test_single_crate_layout(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "shop"\nversion = "0.1.0"\n\n'
        '[package.metadata.domain-powers]\ncontexts = ["ordering", "billing"]\n'
    )
    path = tmp_path / "src" / "ordering" / "domain" / "order.rs"
    found = check(path, "use crate::billing::domain::Payment;\nuse crate::billing::api::Pay;\n")
    assert found == [(1, "CROSS-CTX"), (1, "DOMAIN-DEP"), (2, "DOMAIN-DEP")]
    app = tmp_path / "src" / "ordering" / "application.rs"
    assert check(app, "use crate::billing::api::Pay;\nuse crate::billing::domain::P;\n") == [
        (2, "CROSS-CTX")
    ]


def test_no_config_infers_domain_from_dir(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    path = tmp_path / "src" / "domain" / "order.rs"
    found = check(path, "use crate::infrastructure::Db;\nuse sqlx::Pool;\nuse crate::domain::X;\n")
    assert found == [(1, "DOMAIN-DEP"), (2, "DOMAIN-DEP")]


def test_extra_forbidden_from_config(ws: Path) -> None:
    text = WORKSPACE + 'domain_forbidden = ["legacy_sdk"]\n'
    (ws / "Cargo.toml").write_text(text)
    assert check(domain_file(ws), "use legacy_sdk::Thing;\n") == [(1, "DOMAIN-DEP")]


def test_unbalanced_file_does_not_crash(ws: Path) -> None:
    found = check(domain_file(ws), 'fn f() {\n  a.unwrap();\n  let s = "open\n')
    assert found == [(2, "PANIC")]


# ---------------------------------------------------------------- hook


def run_hook(
    root: Path, tool: str, tool_input: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"cwd": str(root), "tool_name": tool, "tool_input": tool_input}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_hook_edit_on_rs_reports_changed_lines_only(ws: Path) -> None:
    path = domain_file(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fn legacy() { a.unwrap(); }\nfn added() { b.unwrap(); }\n")
    result = run_hook(
        ws,
        "Edit",
        {"file_path": str(path), "old_string": "x", "new_string": "fn added() { b.unwrap(); }"},
    )
    assert result.returncode == 2
    assert "order.rs:2: [PANIC]" in result.stderr
    assert "order.rs:1:" not in result.stderr


def test_codex_patch_on_rs(ws: Path) -> None:
    path = domain_file(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("use sqlx::PgPool;\n")
    rel = path.relative_to(ws).as_posix()
    patch = f"*** Begin Patch\n*** Add File: {rel}\n+use sqlx::PgPool;\n*** End Patch"
    result = run_hook(ws, "apply_patch", {"command": patch})
    assert result.returncode == 2
    assert "[DOMAIN-DEP]" in result.stderr


def test_scan_skips_target_dir(ws: Path) -> None:
    bad = ws / "target" / "debug" / "build" / "x.rs"
    bad.parent.mkdir(parents=True)
    bad.write_text("fn f() { unsafe {} }\n")
    good = ws / "crates" / "ordering" / "src" / "lib.rs"
    good.write_text("pub mod api;\n")
    result = subprocess.run(
        [sys.executable, str(GUARD), "--scan", str(ws)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
