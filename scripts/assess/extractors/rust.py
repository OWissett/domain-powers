#!/usr/bin/env python3
"""Rust extractor: writes the neutral model (domain-powers.assess.model/1) for a source tree.

Usage: rust.py <source_root> --out model.json [--package NAME] [--include-tests]
               [--exclude GLOB ...]

<source_root> is a workspace or crate directory (or any directory holding crates). Units
are `.rs` files under each crate's `src/`, named `crate::module::path`. Escape and
framework detection come from the guard's Rust pack, so the counts match what the guard
reports. Standard library only. This is a separate command: it does not import the core.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the directory holding languages/

from languages import rust as pack
from languages.base import escape_counts, justify

Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]

MODEL_SCHEMA = "domain-powers.assess.model/1"
CAPABILITIES_DECLARED = ("data_only", "edges", "escapes", "framework_refs", "layer_hints", "types")
SKIP_DIRS = frozenset({"target", "node_modules", "vendor"})
TEST_DIRS = ("tests", "benches", "examples")

HINTS = frozenset(
    {
        "models",
        "entities",
        "schemas",
        "services",
        "managers",
        "handlers",
        "views",
        "controllers",
        "routes",
        "api",
        "repositories",
        "dao",
        "serializers",
        "forms",
        "tasks",
        "utils",
        "helpers",
        "common",
        "core",
        "domain",
        "application",
        "infrastructure",
        "adapters",
        "tests",
    }
)
HINT_ALIASES = {
    "model": "models",
    "entity": "entities",
    "schema": "schemas",
    "service": "services",
    "manager": "managers",
    "handler": "handlers",
    "view": "views",
    "controller": "controllers",
    "route": "routes",
    "repos": "repositories",
    "repo": "repositories",
    "repository": "repositories",
    "serializer": "serializers",
    "form": "forms",
    "task": "tasks",
    "util": "utils",
    "helper": "helpers",
    "adapter": "adapters",
    "infra": "infrastructure",
}

TYPE_RE = re.compile(rf"\b(struct|enum|union|trait)\s+({pack.IDENT})")
IMPL_RE = re.compile(r"\bimpl\b")
FN_RE = re.compile(rf"\bfn\s+({pack.IDENT})")
ACCESSOR_RE = re.compile(r"^\{\s*&?\s*(?:mut\s+)?self\s*\.\s*\w+\s*(?:\.\s*clone\s*\(\s*\))?\s*\}$")
CONSTRUCTOR_PREFIXES = ("from_", "with_")
CONSTRUCTORS = frozenset({"new", "default"})


@dataclass(frozen=True)
class Crate:
    name: str  # identifier form (hyphens become underscores)
    directory: Path  # relative to the current directory, as given


@dataclass(frozen=True)
class FileUnit:
    crate: Crate
    rel: str  # path relative to the crate directory, posix
    module: tuple[str, ...]
    unit_id: str
    is_test: bool


# ---------------------------------------------------------------- discovery


def _skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def _crate_name(manifest: Path) -> str | None:
    data = pack.read_toml(manifest)
    package = None if data is None else data.get("package")
    if isinstance(package, dict) and isinstance(package.get("name"), str):
        return pack.ident(package["name"])
    return None


def find_crates(root: Path) -> list[Crate]:
    """Every package under root; if none, the package root itself belongs to."""
    crates: list[Crate] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
        if "Cargo.toml" in files:
            name = _crate_name(Path(current) / "Cargo.toml")
            if name is not None:
                crates.append(Crate(name, Path(current)))
    if not crates:
        found = pack.crate_of(root.resolve())
        if found is not None:
            crates.append(Crate(found[0], Path(os.path.relpath(found[1]))))
    return sorted(crates, key=lambda c: c.name)


def _rs_files(directory: Path) -> list[str]:
    found: list[str] = []
    for current, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
        here = Path(current)
        if (here / "Cargo.toml").is_file() and here != directory:
            dirs[:] = []  # a nested crate is found on its own
            continue
        found.extend(
            (here / n).relative_to(directory).as_posix() for n in files if n.endswith(".rs")
        )
    return sorted(found)


def _unit_for(crate: Crate, rel: str, *, has_lib: bool) -> FileUnit | None:
    parts = tuple(rel.split("/"))
    if parts[0] in TEST_DIRS:
        stem = parts[-1].removesuffix(".rs")
        tested = ("tests", *parts[1:-1], stem) if stem != "main" else ("tests", *parts[1:-1])
        return FileUnit(crate, rel, tested, "::".join((crate.name, *tested)), is_test=True)
    if parts[0] != "src":
        return None  # build.rs and other files outside src/
    inner = parts[1:]
    if inner[:1] == ("bin",):
        module: tuple[str, ...] = ("bin", *(p.removesuffix(".rs") for p in inner[1:]))
    elif inner == ("main.rs",) and has_lib:
        module = ("main",)
    else:
        module = tuple(pack.module_path(inner))
    return FileUnit(crate, rel, module, "::".join((crate.name, *module)), is_test=False)


# ---------------------------------------------------------------- per-file facts


def _group(unit: FileUnit, root_crate: str | None) -> str:
    if root_crate is None or unit.crate.name != root_crate or not unit.module:
        return unit.crate.name
    first = unit.module[0]
    is_parent = (
        len(unit.module) > 1
        or unit.rel.endswith("/mod.rs")
        or (unit.crate.directory / "src" / first).is_dir()
    )
    return f"{unit.crate.name}::{first}" if is_parent else unit.crate.name


def _layer_hint(unit: FileUnit) -> str | None:
    if unit.is_test:
        return "tests"
    candidates = [*unit.crate.name.split("_"), *unit.module]
    for segment in reversed(candidates):
        name = HINT_ALIASES.get(segment, segment)
        if name in HINTS and name != "tests":
            return name
    return None


def _in_domain(unit: FileUnit) -> bool:
    return "domain" in unit.module or unit.crate.name.endswith("_domain")


def _loc(text: str) -> int:
    count = 0
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("//", "/*", "*")):
            count += 1
    return count


def _depths(masked: str) -> list[int]:
    """Brace depth before each character."""
    depths: list[int] = []
    depth = 0
    for ch in masked:
        depths.append(depth)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
    return depths


def _block_end(masked: str, brace: int) -> int:
    depth = 0
    for k in range(brace, len(masked)):
        if masked[k] == "{":
            depth += 1
        elif masked[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(masked) - 1


def _skip_generics(text: str, i: int) -> int:
    """Index after a `<...>` group starting at i (nested), or i if none."""
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "<":
        return i
    depth = 0
    for k in range(i, len(text)):
        if text[k] == "<":
            depth += 1
        elif text[k] == ">" and text[k - 1] != "-":
            depth -= 1
            if depth == 0:
                return k + 1
    return len(text)


def _inherent_impls(masked: str, depths: list[int]) -> dict[str, list[str]]:
    """Type name → bodies of its inherent (non-trait) impl blocks at file level."""
    impls: dict[str, list[str]] = {}
    for m in IMPL_RE.finditer(masked):
        if depths[m.start()] != 0:
            continue
        brace = masked.find("{", m.end())
        semi = masked.find(";", m.end())
        if brace < 0 or 0 <= semi < brace:
            continue
        header = masked[m.end() : brace]
        if re.search(r"\bfor\b", header):
            continue  # a trait impl: like dunder methods, it does not make a type behavioural
        start = _skip_generics(header, 0)
        name = re.match(rf"\s*(?:[\w:]+::)?({pack.IDENT})", header[start:])
        if name is None:
            continue
        end = _block_end(masked, brace)
        impls.setdefault(name.group(1), []).append(masked[brace + 1 : end])
    return impls


def _is_data_method(name: str, body: str) -> bool:
    if name in CONSTRUCTORS or name.startswith(CONSTRUCTOR_PREFIXES):
        return True
    return bool(ACCESSOR_RE.match(body.strip()))


def _methods(impl_body: str) -> list[tuple[str, str]]:
    """(name, body with braces) for each method in an impl body."""
    out: list[tuple[str, str]] = []
    depths = _depths(impl_body)
    for m in FN_RE.finditer(impl_body):
        if depths[m.start()] != 0:
            continue
        brace = impl_body.find("{", m.end())
        semi = impl_body.find(";", m.end())
        if brace < 0 or 0 <= semi < brace:
            out.append((m.group(1), ""))
            continue
        end = _block_end(impl_body, brace)
        out.append((m.group(1), impl_body[brace : end + 1]))
    return out


def _types(src: pack.Source) -> list[Json]:
    depths = _depths(src.masked)
    impls = _inherent_impls(src.masked, depths)
    out: list[Json] = []
    for m in TYPE_RE.finditer(src.masked):
        line = pack.line_of(src.masked, m.start())
        if depths[m.start()] != 0 or src.in_test(line):
            continue
        kind, name = m.group(1), m.group(2).removeprefix("r#")
        if kind == "trait":
            data_only = False
        else:
            methods = [mm for body in impls.get(name, []) for mm in _methods(body)]
            data_only = all(_is_data_method(n, b) for n, b in methods)
        out.append({"name": name, "data_only": data_only})
    return out


# ---------------------------------------------------------------- extraction


def extract(
    source_root: Path,
    *,
    package: str | None = None,
    include_tests: bool = False,
    exclude: Sequence[str] = (),
) -> dict[str, Json]:
    crates = find_crates(source_root)
    names = [c.name for c in crates]
    root_crate: str | None
    if package is not None:
        root_crate = pack.ident(package)
        if root_crate not in names:
            raise ValueError(f"crate not found: {package}")
    else:
        root_crate = names[0] if len(names) == 1 else None

    candidates: list[FileUnit] = []
    for crate in crates:
        rels = _rs_files(crate.directory)
        has_lib = "src/lib.rs" in rels
        for rel in rels:
            unit = _unit_for(crate, rel, has_lib=has_lib)
            if unit is None or (unit.is_test and not include_tests):
                continue
            shown = (crate.directory / rel).relative_to(source_root).as_posix()
            if any(fnmatch.fnmatch(shown, g) or fnmatch.fnmatch(rel, g) for g in exclude):
                continue
            candidates.append(unit)

    skipped: list[tuple[str, str]] = []
    units: dict[str, dict[str, Json]] = {}
    sources: dict[str, tuple[FileUnit, pack.Source]] = {}
    for unit in candidates:
        path = unit.crate.directory / unit.rel
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            skipped.append((path.as_posix(), "not UTF-8"))
            continue
        if unit.unit_id in units:
            skipped.append((path.as_posix(), "duplicate module id"))
            continue
        src = pack.Source.of(text)
        found = pack.escape_findings(path, src, is_test=unit.is_test)
        abs_paths = src.paths(unit.crate.name, list(unit.module))
        refs: list[Json] = list(pack.framework_refs(abs_paths, src))
        escapes: dict[str, Json] = dict(
            escape_counts(justify(found, text, in_domain=_in_domain(unit)))
        )
        units[unit.unit_id] = {
            "id": unit.unit_id,
            "path": path.as_posix(),
            "group": _group(unit, root_crate),
            "loc": _loc(text),
            "layer_hint": _layer_hint(unit),
            "types": _types(src),
            "escapes": escapes,
            "framework_refs": refs,
        }
        sources[unit.unit_id] = (unit, src)

    ids = frozenset(units)
    counts: dict[tuple[str, str], int] = {}
    for unit_id, (unit, src) in sources.items():
        for line, abs_path in src.paths(unit.crate.name, list(unit.module)):
            if src.in_test(line) and not include_tests:
                continue
            target = _longest_unit_prefix(abs_path, ids)
            if target is not None and target != unit_id:
                counts[(unit_id, target)] = counts.get((unit_id, target), 0) + 1

    return {
        "schema": MODEL_SCHEMA,
        "language": "rust",
        "root": source_root.as_posix(),
        "capabilities": list(CAPABILITIES_DECLARED),
        "units": [units[i] for i in sorted(units)],
        "edges": [{"from": s, "to": t, "count": c} for (s, t), c in sorted(counts.items())],
        "skipped": [{"path": p, "reason": r} for p, r in sorted(skipped)],
    }


def _longest_unit_prefix(abs_path: list[str], ids: frozenset[str]) -> str | None:
    for end in range(len(abs_path), 0, -1):
        candidate = "::".join(abs_path[:end])
        if candidate in ids:
            return candidate
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rust.py", description="Extract the neutral model from a Rust workspace or crate."
    )
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return 0 if exit_.code == 0 else 2
    source_root: Path = args.source_root
    if not source_root.is_dir():
        print(f"error: not a readable directory: {source_root}", file=sys.stderr)
        return 2
    try:
        model = extract(
            source_root,
            package=args.package,
            include_tests=args.include_tests,
            exclude=args.exclude,
        )
        args.out.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
