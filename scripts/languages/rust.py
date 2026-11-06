"""Rust language pack: type escapes and boundary rules for `.rs` files.

Configuration: [workspace.metadata.domain-powers] or [package.metadata.domain-powers] in
the nearest Cargo.toml that has one:

    contexts = ["ordering", "billing"]   # context crates, or modules in a single crate
    shared = ["shared_kernel"]
    public_module = "api"
    domain_forbidden = []                # extra crates or paths, merged with the defaults

A small lexer masks comments and literals; `use` trees and qualified paths are resolved
against the file's crate and module. The compiler, clippy and cargo-deny give the exact
answers in the gates; this pack gives fast feedback on the lines just written.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from languages.base import LAYERS, Finding, justify

DEFAULT_DOMAIN_FORBIDDEN = (
    "sqlx",
    "diesel",
    "sea_orm",
    "rusqlite",
    "postgres",
    "tokio_postgres",
    "mongodb",
    "redis",
    "reqwest",
    "hyper",
    "axum",
    "actix_web",
    "rocket",
    "warp",
    "tonic",
    "tower",
    "tokio",
    "async_std",
    "serde",
    "serde_json",
    "aws_sdk_*",
    "aws_config",
    "std::fs",
    "std::net",
    "std::process",
    "std::env",
)
TEST_DIRS = ("tests", "benches", "examples")

IDENT = r"(?:r#)?[A-Za-z_][A-Za-z0-9_]*"
USE_RE = re.compile(r"\b(?:use|extern\s+crate)\b")
QUALIFIED_RE = re.compile(rf"(?<![\w:])(?:::\s*)?{IDENT}(?:\s*::\s*{IDENT})+")
MOD_RE = re.compile(rf"\bmod\s+({IDENT})\s*[;{{]")
CFG_TEST_RE = re.compile(r"#\s*\[\s*cfg\s*\(\s*test\s*\)\s*\]")
TOKEN_RE = re.compile(rf"::|[{{}},*;]|{IDENT}")

UNSAFE_RE = re.compile(r"\bunsafe\b")
PANIC_RE = re.compile(
    r"\.\s*unwrap\s*\(\s*\)|\.\s*expect\s*\(|\b(?:panic|todo|unimplemented|unreachable)\s*!"
)
NUMERIC = "u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|isize|f32|f64"
CAST_RE = re.compile(rf"\bas\s+(?:{NUMERIC})\b|\btransmute\b")
ANY_RE = re.compile(r"\b(?:dyn|impl)\s+Any\b|\bany\s*::\s*Any\b|\.\s*downcast(?:_ref|_mut)?\b")
IGNORE_RE = re.compile(r"#\s*!?\s*\[\s*(?:allow|expect)\s*\(")

MESSAGES = {
    "UNSAFE": "unsafe switches the compiler's guarantees off. Use a safe API or wrap the unsafe "
    "code in a small, audited infrastructure module.",
    "PANIC": "a panic hides a failure the types should carry. Return a Result or make the state "
    "unrepresentable (domain-powers:type-driven-design).",
    "CAST": "an `as` or transmute conversion can truncate or reinterpret silently. Use "
    "From/TryFrom, or a value type that cannot hold the bad value.",
    "ANY": "Any erases the type. Use an enum of the cases, a trait, or a generic.",
    "IGNORE": "lint suppression. Fix the code so the lint agrees.",
}


# ---------------------------------------------------------------- lexer


def _blank(chars: list[str], start: int, end: int) -> None:
    for k in range(start, min(end, len(chars))):
        if chars[k] != "\n":
            chars[k] = " "


def _raw_string_end(src: str, i: int) -> int | None:
    """If a raw string starts at i (`r"`, `r#"`, `br"`...), return the index after it."""
    j = i
    if src.startswith(("br", "cr"), j):
        j += 2
    elif src.startswith("r", j):
        j += 1
    else:
        return None
    hashes = 0
    while j < len(src) and src[j] == "#":
        hashes += 1
        j += 1
    if j >= len(src) or src[j] != '"':
        return None
    close = '"' + "#" * hashes
    end = src.find(close, j + 1)
    return len(src) if end < 0 else end + len(close)


def mask(src: str) -> str:
    """Blank comments and the contents of string and char literals, keeping length and lines."""
    chars = list(src)
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        prev_ident = i > 0 and (src[i - 1].isalnum() or src[i - 1] == "_")
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            _blank(chars, i, end)
            i = end
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            _blank(chars, i, j)
            i = j
        elif c in "rbc" and not prev_ident and (raw_end := _raw_string_end(src, i)) is not None:
            _blank(chars, i, raw_end)
            i = raw_end
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            _blank(chars, i + 1, j)
            i = j + 1
        elif c == "'":
            if i + 1 < n and src[i + 1] == "\\":
                j = src.find("'", i + 3)
                j = n if j < 0 else j
                _blank(chars, i + 1, j)
                i = j + 1
            elif i + 2 < n and src[i + 2] == "'":
                _blank(chars, i + 1, i + 2)
                i += 3
            else:
                i += 1  # a lifetime or label
        else:
            i += 1
    return "".join(chars)


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _statement_end(masked: str, start: int) -> int:
    """Index of the `;` ending the item that starts at `start` (end of text if none)."""
    end = masked.find(";", start)
    return len(masked) if end < 0 else end


def _parse_tree(
    tokens: list[tuple[str, int]], pos: int, prefix: list[str]
) -> tuple[list[tuple[int, list[str]]], int]:
    """Parse one use tree; return its expanded (line, path) leaves and the next position."""
    path = list(prefix)
    if pos < len(tokens) and tokens[pos][0] == "::" and not path:
        path.append("::")
        pos += 1
    while pos < len(tokens):
        tok, line = tokens[pos]
        if tok == "{":
            leaves: list[tuple[int, list[str]]] = []
            pos += 1
            while pos < len(tokens) and tokens[pos][0] != "}":
                if tokens[pos][0] == ",":
                    pos += 1
                    continue
                found, pos = _parse_tree(tokens, pos, path)
                leaves.extend(found)
            return leaves, pos + 1
        if tok == "*":
            return [(line, path)], pos + 1
        if tok in (",", "}", ";", "::"):
            return [], pos
        if tok != "self" or not path:
            path.append(tok.removeprefix("r#"))
        pos += 1
        if pos < len(tokens) and tokens[pos][0] == "::":
            pos += 1
            continue
        if pos < len(tokens) and tokens[pos][0] == "as":
            pos += 2  # drop the rename
        return [(line, path)], pos
    return [], pos


def use_paths(masked: str) -> list[tuple[int, list[str]]]:
    """Every path a `use` or `extern crate` item names, expanded, with the line of its leaf."""
    found: list[tuple[int, list[str]]] = []
    for m in USE_RE.finditer(masked):
        end = _statement_end(masked, m.end())
        body = masked[m.end() : end]
        tokens = [
            (t.group(0), line_of(masked, m.end() + t.start())) for t in TOKEN_RE.finditer(body)
        ]
        leaves, _ = _parse_tree(tokens, 0, [])
        found.extend((line, path) for line, path in leaves if path and path != ["::"])
    return found


def _use_spans(masked: str) -> list[tuple[int, int]]:
    return [(m.start(), _statement_end(masked, m.end())) for m in USE_RE.finditer(masked)]


def qualified_paths(masked: str) -> list[tuple[int, list[str]]]:
    """Paths written in code (`a::b::c`) outside `use` items, with their line."""
    spans = _use_spans(masked)
    found: list[tuple[int, list[str]]] = []
    for m in QUALIFIED_RE.finditer(masked):
        if any(start <= m.start() < end for start, end in spans):
            continue
        text = m.group(0)
        segments = [s.strip().removeprefix("r#") for s in text.split("::")]
        if segments and segments[0] == "":
            segments = ["::", *segments[1:]]
        found.append((line_of(masked, m.start()), segments))
    return found


def local_modules(masked: str) -> set[str]:
    """Modules declared in this file (`mod x;` or `mod x { }`)."""
    return {m.group(1).removeprefix("r#") for m in MOD_RE.finditer(masked)}


def test_ranges(masked: str) -> list[tuple[int, int]]:
    """Line ranges (inclusive) of items marked `#[cfg(test)]`."""
    ranges: list[tuple[int, int]] = []
    for m in CFG_TEST_RE.finditer(masked):
        brace = masked.find("{", m.end())
        semi = masked.find(";", m.end())
        if brace < 0 or (0 <= semi < brace):
            end = len(masked) if semi < 0 else semi
        else:
            depth, end = 0, len(masked)
            for k in range(brace, len(masked)):
                if masked[k] == "{":
                    depth += 1
                elif masked[k] == "}":
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
        ranges.append((line_of(masked, m.start()), line_of(masked, end)))
    return ranges


def resolve(segments: list[str], crate: str, module: list[str], local: set[str]) -> list[str]:
    """Make a path absolute. Paths inside this crate start with the crate's name."""
    if not segments:
        return []
    head, rest = segments[0], segments[1:]
    if head == "::":
        return rest
    if head == "crate":
        return [crate, *rest]
    if head == "self":
        return [crate, *module, *rest]
    if head == "super":
        base = list(module)
        while segments and segments[0] == "super":
            base = base[:-1]
            segments = segments[1:]
        return [crate, *base, *segments]
    if head in local:
        return [crate, *module, *segments]
    return list(segments)


# ---------------------------------------------------------------- config and location


@dataclass(frozen=True)
class RustConfig:
    project_root: Path | None = None
    contexts: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    public_module: str = "api"
    domain_forbidden: tuple[str, ...] = DEFAULT_DOMAIN_FORBIDDEN


@dataclass
class RustLocation:
    crate: str = "crate"
    module: list[str] = field(default_factory=list)
    context: str | None = None
    layer: str | None = None
    is_test: bool = False


def ident(name: str) -> str:
    return name.replace("-", "_")


def read_toml(path: Path) -> dict[str, object] | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _metadata(data: dict[str, object]) -> dict[str, object] | None:
    for table in ("workspace", "package"):
        section = data.get(table)
        if isinstance(section, dict):
            meta = section.get("metadata")
            if isinstance(meta, dict):
                found = meta.get("domain-powers")
                if isinstance(found, dict):
                    return found
    return None


def _strings(raw: object) -> tuple[str, ...]:
    return tuple(ident(str(x)) for x in raw) if isinstance(raw, list) else ()


@lru_cache(maxsize=256)
def load_config(start: Path) -> RustConfig:
    for directory in [start, *start.parents]:
        candidate = directory / "Cargo.toml"
        if not candidate.is_file():
            continue
        data = read_toml(candidate)
        section = None if data is None else _metadata(data)
        if section is None:
            continue
        extra = section.get("domain_forbidden", [])
        return RustConfig(
            project_root=directory,
            contexts=_strings(section.get("contexts")),
            shared=_strings(section.get("shared")),
            public_module=str(section.get("public_module", "api")),
            domain_forbidden=DEFAULT_DOMAIN_FORBIDDEN
            + (tuple(str(x) for x in extra) if isinstance(extra, list) else ()),
        )
    return RustConfig()


@lru_cache(maxsize=256)
def crate_of(start: Path) -> tuple[str, Path] | None:
    """The nearest package's crate name (as an identifier) and directory."""
    for directory in [start, *start.parents]:
        candidate = directory / "Cargo.toml"
        if not candidate.is_file():
            continue
        data = read_toml(candidate)
        package = None if data is None else data.get("package")
        if isinstance(package, dict) and isinstance(package.get("name"), str):
            return ident(package["name"]), directory
    return None


def module_path(rel: tuple[str, ...]) -> list[str]:
    """Module path of a file relative to its crate's `src/`."""
    parts = list(rel)
    if parts and parts[0] == "bin":
        return []
    if not parts:
        return []
    stem = parts[-1].removesuffix(".rs")
    if stem in ("lib", "main") and len(parts) == 1:
        return []
    if stem == "mod":
        return parts[:-1]
    return [*parts[:-1], stem]


def split_crate(crate: str, cfg: RustConfig) -> tuple[str | None, str | None]:
    """(context, layer) a crate name stands for: `ordering` or `ordering_domain`."""
    if crate in cfg.contexts:
        return crate, None
    for layer in LAYERS:
        ctx = crate.removesuffix(f"_{layer}")
        if ctx != crate and ctx in cfg.contexts:
            return ctx, layer
    return None, None


def locate(path: Path, cfg: RustConfig) -> RustLocation:
    loc = RustLocation()
    resolved = path.resolve()
    found = crate_of(resolved.parent)
    rel: tuple[str, ...] = resolved.parts
    if found is not None:
        loc.crate, crate_dir = found
        rel = resolved.relative_to(crate_dir).parts
        if rel and rel[0] == "src":
            loc.module = module_path(rel[1:])
        else:
            loc.is_test = bool(rel) and rel[0] in TEST_DIRS
    if not cfg.contexts:
        dirs = [*rel[:-1], *loc.module]
        for name in LAYERS:
            if name in dirs:
                loc.layer = name
        return loc
    ctx, layer = split_crate(loc.crate, cfg)
    if ctx is not None:
        loc.context = ctx
        loc.layer = layer if layer is not None else _layer_at(loc.module, 0)
    elif loc.module and loc.module[0] in cfg.contexts:
        loc.context = loc.module[0]
        loc.layer = _layer_at(loc.module, 1)
    return loc


def _layer_at(module: list[str], i: int) -> str | None:
    return module[i] if len(module) > i and module[i] in LAYERS else None


@dataclass(frozen=True)
class Target:
    """Where an absolute path points, relative to the configured contexts."""

    context: str | None
    layer: str | None  # the segment after the context: a layer, the public module, or other
    workspace: bool  # inside this crate or a configured context or shared crate
    shared: bool


def classify(abs_path: list[str], loc: RustLocation, cfg: RustConfig) -> Target:
    if not abs_path:
        return Target(None, None, workspace=False, shared=False)
    head = abs_path[0]
    own = head == loc.crate
    if head in cfg.shared or (own and len(abs_path) > 1 and abs_path[1] in cfg.shared):
        return Target(None, None, workspace=True, shared=True)
    ctx, layer = split_crate(head, cfg)
    if ctx is not None:
        return Target(ctx, layer or _seg(abs_path, 1), workspace=True, shared=False)
    if own and len(abs_path) > 1 and abs_path[1] in cfg.contexts:
        return Target(abs_path[1], _seg(abs_path, 2), workspace=True, shared=False)
    return Target(None, _seg(abs_path, 1) if own else None, workspace=own, shared=False)


def _seg(parts: list[str], i: int) -> str | None:
    return parts[i] if len(parts) > i else None


def forbidden_match(abs_path: list[str], forbidden: tuple[str, ...]) -> str | None:
    """The forbidden entry this path falls under, if any (`std::fs`, `aws_sdk_*`, `sqlx`)."""
    if not abs_path:
        return None
    for entry in forbidden:
        parts = entry.split("::")
        if len(parts) > 1:
            if abs_path[: len(parts)] == parts:
                return entry
        elif fnmatch.fnmatchcase(abs_path[0], entry):
            return abs_path[0]
    return None


# ---------------------------------------------------------------- analysis


@dataclass(frozen=True)
class Source:
    """A file's masked text and the facts both the guard and the extractor need."""

    raw: str
    masked: str
    tests: tuple[tuple[int, int], ...]
    local: frozenset[str]

    @staticmethod
    def of(raw: str) -> Source:
        masked = mask(raw)
        return Source(raw, masked, tuple(test_ranges(masked)), frozenset(local_modules(masked)))

    def in_test(self, line: int) -> bool:
        return any(start <= line <= end for start, end in self.tests)

    def paths(self, crate: str, module: list[str]) -> list[tuple[int, list[str]]]:
        """Absolute paths from `use` items and qualified paths, with their lines."""
        local = set(self.local)
        written = use_paths(self.masked) + qualified_paths(self.masked)
        return sorted(
            ((line, resolve(segments, crate, module, local)) for line, segments in written),
            key=lambda item: item[0],
        )


def escape_findings(path: Path, src: Source, *, is_test: bool) -> list[Finding]:
    """Type-escape findings before justifications. In test code only suppressions count."""
    findings: list[Finding] = []
    patterns = (("UNSAFE", UNSAFE_RE), ("PANIC", PANIC_RE), ("CAST", CAST_RE), ("ANY", ANY_RE))
    for code, pattern in (*patterns, ("IGNORE", IGNORE_RE)):
        for m in pattern.finditer(src.masked):
            line = line_of(src.masked, m.start())
            if code != "IGNORE" and (is_test or src.in_test(line)):
                continue
            findings.append(Finding(path, line, code, MESSAGES[code]))
    for line, segments in use_paths(src.masked):
        is_any = segments[-1] == "Any" and segments[:2] in (["std", "any"], ["core", "any"])
        if is_any and not (is_test or src.in_test(line)):
            findings.append(Finding(path, line, "ANY", MESSAGES["ANY"]))
    return findings


def framework_refs(
    paths: list[tuple[int, list[str]]],
    src: Source,
    forbidden: tuple[str, ...] = DEFAULT_DOMAIN_FORBIDDEN,
) -> list[str]:
    """Framework or I/O crates and std modules used outside test code, sorted."""
    refs = {
        match
        for line, abs_path in paths
        if not src.in_test(line) and (match := forbidden_match(abs_path, forbidden)) is not None
    }
    return sorted(refs)


def _domain_finding(
    path: Path, line: int, abs_path: list[str], loc: RustLocation, cfg: RustConfig
) -> Finding | None:
    shown = "::".join(abs_path)
    hit = forbidden_match(abs_path, cfg.domain_forbidden)
    if hit is not None:
        return Finding(
            path,
            line,
            "DOMAIN-DEP",
            f"domain layer uses '{hit}'. Keep domain pure: define a trait port in domain and "
            "implement it in infrastructure (domain-powers:designing-boundaries).",
        )
    target = classify(abs_path, loc, cfg)
    if not cfg.contexts:
        if any(p in ("infrastructure", "application") for p in abs_path):
            return Finding(
                path,
                line,
                "DOMAIN-DEP",
                f"domain layer uses '{shown}' from an outer layer. Dependencies point inward.",
            )
        return None
    if not target.workspace or target.shared:
        return None
    if target.context == loc.context and target.layer == "domain":
        return None
    shared = ", ".join(cfg.shared) or "none configured"
    return Finding(
        path,
        line,
        "DOMAIN-DEP",
        f"domain layer uses '{shown}'. Domain may use only its own context's domain and the "
        f"shared kernel ({shared}).",
    )


def check_paths(path: Path, src: Source, loc: RustLocation, cfg: RustConfig) -> list[Finding]:
    findings: list[Finding] = []
    for line, abs_path in src.paths(loc.crate, loc.module):
        test_code = loc.is_test or src.in_test(line)
        if loc.layer == "domain" and not test_code:
            found = _domain_finding(path, line, abs_path, loc, cfg)
            if found is not None:
                findings.append(found)
        target = classify(abs_path, loc, cfg)
        if (
            loc.layer == "application"
            and not test_code
            and target.context == loc.context
            and loc.context is not None
            and target.layer == "infrastructure"
        ):
            findings.append(
                Finding(
                    path,
                    line,
                    "LAYER",
                    f"application uses '{'::'.join(abs_path)}'. Depend on a trait port; wire the "
                    "adapter in the composition root.",
                )
            )
        crosses = (
            loc.context is not None and target.context is not None and target.context != loc.context
        )
        if crosses and target.layer != cfg.public_module:
            shown = "::".join(abs_path)
            findings.append(
                Finding(
                    path,
                    line,
                    "CROSS-CTX",
                    f"context '{loc.context}' uses '{shown}'. Other contexts may only "
                    f"use '{target.context}::{cfg.public_module}' (DTOs, commands, integration "
                    "events).",
                )
            )
    return findings


class RustPack:
    name = "rust"
    suffixes = (".rs",)

    def analyse(self, path: Path, source: str) -> list[Finding]:
        cfg = load_config(path.parent.resolve())
        loc = locate(path, cfg)
        src = Source.of(source)
        findings = escape_findings(path, src, is_test=loc.is_test)
        findings += check_paths(path, src, loc, cfg)
        kept = justify(findings, source, in_domain=loc.layer == "domain")
        return sorted(set(kept), key=lambda f: (f.line, f.code))

    def expand_changed(self, source: str, lines: set[int]) -> set[int]:
        """Findings are reported on the line of the token or path itself, so no expansion."""
        return lines


PACK = RustPack()
