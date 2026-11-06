"""Tests for the Rust pack's lexer and path handling."""

from languages import rust


def test_lexer_keeps_length_and_newlines() -> None:
    src = 'let s = "a\nb"; // c\n/* d\n e */ x'
    masked = rust.mask(src)
    assert len(masked) == len(src)
    assert masked.count("\n") == src.count("\n")


def test_lexer_masks_line_and_nested_block_comments() -> None:
    src = "a // x.unwrap()\n/* outer /* inner */ still.unwrap() */ b.unwrap()\n"
    masked = rust.mask(src)
    assert masked.count("unwrap") == 1
    assert "b.unwrap()" in masked


def test_lexer_masks_strings_raw_strings_and_chars() -> None:
    src = (
        'let a = "x.unwrap() \\" y.unwrap()";\n'
        'let b = r#"z.unwrap() " still"#;\n'
        'let c = b"unsafe";\n'
        "let d = '\"'; let e = '\\''; let f = '{';\n"
        "real.unwrap();\n"
    )
    masked = rust.mask(src)
    assert masked.count("unwrap") == 1
    assert "unsafe" not in masked
    assert "real.unwrap()" in masked
    assert masked.count("{") == 0


def test_lexer_lifetime_is_not_char() -> None:
    src = "fn f<'a>(x: &'a str) -> &'a str { x.unwrap() }\n"
    masked = rust.mask(src)
    assert "x.unwrap()" in masked
    assert "'a" in masked


def test_lexer_unterminated_string_masks_to_eof() -> None:
    src = 'x.unwrap();\nlet s = "never closed\ny.unwrap();\n'
    masked = rust.mask(src)
    assert "x.unwrap()" in masked
    assert "y.unwrap()" not in masked


def test_use_tree_groups_and_renames() -> None:
    masked = rust.mask("use crate::a::{b::{C, D as E}, self};\npub use ::ext::*;\n")
    assert rust.use_paths(masked) == [
        (1, ["crate", "a", "b", "C"]),
        (1, ["crate", "a", "b", "D"]),
        (1, ["crate", "a"]),
        (2, ["::", "ext"]),
    ]


def test_use_tree_multiline_reports_leaf_lines() -> None:
    masked = rust.mask("use std::{\n    fs,\n    io::Write,\n};\n")
    assert rust.use_paths(masked) == [(2, ["std", "fs"]), (3, ["std", "io", "Write"])]


def test_extern_crate_is_a_use() -> None:
    assert rust.use_paths(rust.mask("extern crate serde;\n")) == [(1, ["serde"])]


def test_qualified_paths_skip_use_lines() -> None:
    masked = rust.mask(
        'use sqlx::PgPool;\nfn f() { let x = sqlx::query!("q"); Vec::<u8>::new(); a::b::c(); }\n'
    )
    assert rust.qualified_paths(masked) == [
        (2, ["sqlx", "query"]),
        (2, ["a", "b", "c"]),
    ]


def test_cfg_test_range() -> None:
    src = "fn a() {}\n#[cfg(test)]\nmod tests {\n    fn t() { x.unwrap(); }\n}\nfn b() {}\n"
    assert rust.test_ranges(rust.mask(src)) == [(2, 5)]


def test_local_modules() -> None:
    assert rust.local_modules(rust.mask("mod http;\npub mod api {\n}\n")) == {"http", "api"}


def test_resolve_super_self_crate_and_local() -> None:
    module = ["domain", "order"]
    assert rust.resolve(["crate", "x"], "shop", module, set()) == ["shop", "x"]
    assert rust.resolve(["self", "y"], "shop", module, set()) == ["shop", "domain", "order", "y"]
    assert rust.resolve(["super", "values"], "shop", module, set()) == [
        "shop",
        "domain",
        "values",
    ]
    assert rust.resolve(["super", "super", "api"], "shop", module, set()) == ["shop", "api"]
    assert rust.resolve(["http", "x"], "shop", module, {"http"}) == [
        "shop",
        "domain",
        "order",
        "http",
        "x",
    ]
    assert rust.resolve(["::", "serde"], "shop", module, set()) == ["serde"]
    assert rust.resolve(["sqlx", "PgPool"], "shop", module, set()) == ["sqlx", "PgPool"]


def test_precise_capture_use_is_not_a_use_item() -> None:
    masked = rust.mask(
        "fn f<'a>(x: &'a u8) -> impl Sized + use<'a> { sqlx::query(x); }\n"
        '#[cfg(feature = "x")] use crate::a::B;\n'
        "pub(crate) use super::c::D;\n"
    )
    assert rust.use_paths(masked) == [(2, ["crate", "a", "B"]), (3, ["super", "c", "D"])]
    assert rust.qualified_paths(masked) == [(1, ["sqlx", "query"])]
