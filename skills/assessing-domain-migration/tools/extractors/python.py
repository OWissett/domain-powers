#!/usr/bin/env python3
"""Python extractor: writes the neutral model (domain-powers.assess.model/1) for a source tree.

Usage: python.py <source_root> --out model.json [--package NAME] [--include-tests]
                 [--exclude GLOB ...]

Standard library only. This is a separate command: it does not import the core.
"""

import argparse
import ast
import fnmatch
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]

MODEL_SCHEMA = "domain-powers.assess.model/1"
CAPABILITIES_DECLARED = ("data_only", "edges", "escapes", "framework_refs", "layer_hints", "types")

SKIP_DIRS = frozenset({"__pycache__", "venv", "node_modules", "build", "dist", "site-packages"})

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


def _skip_dir(directory: Path, name: str) -> bool:
    return (
        name in SKIP_DIRS
        or name.startswith(".")
        or name.endswith(".egg-info")
        or (directory / name / "pyvenv.cfg").exists()
    )


def _find_files(root: Path) -> list[str]:
    """Relative posix paths of every candidate .py file, sorted."""
    found: list[str] = []
    for current, dirs, files in os.walk(root):
        here = Path(current)
        dirs[:] = sorted(d for d in dirs if not _skip_dir(here, d))
        for name in files:
            if name.endswith(".py"):
                found.append((here / name).relative_to(root).as_posix())
    return sorted(found)


def _is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (
        any(p in ("tests", "test") for p in parts[:-1])
        or name.removesuffix(".py") in ("tests", "test")
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _module_id(rel: str) -> str:
    parts = rel.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _root_package(root: Path, package: str | None, rels: Sequence[str]) -> str | None:
    if package is not None:
        if not (root / package).is_dir():
            raise ValueError(f"package directory not found: {package}")
        return package
    if any("/" not in r for r in rels):
        return None
    tops = {r.split("/", 1)[0] for r in rels}
    return next(iter(tops)) if len(tops) == 1 else None


def _group(rel: str, module: str, root_package: str | None) -> str:
    segments = module.split(".")
    if root_package is not None and segments[0] == root_package:
        if rel.count("/") < 2:  # noqa: PLR2004
            return root_package
        return ".".join(segments[:2])
    return segments[0]


def _layer_hint(rel: str, module: str, root_package: str | None) -> str | None:
    if _is_test_path(rel):
        return "tests"
    segments = module.split(".")
    if root_package is not None and segments[0] == root_package:
        segments = segments[1:]
    for segment in reversed(segments):
        name = HINT_ALIASES.get(segment, segment)
        if name in HINTS and name != "tests":
            return name
    return None


def _loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if (s := line.strip()) and not s.startswith("#"))


def _resolve_from(node: ast.ImportFrom, module: str, *, is_package: bool) -> str | None:
    if node.level == 0:
        return node.module
    base = module.split(".") if module else []
    if not is_package:
        base = base[:-1]
    if node.level > 1:
        if node.level - 1 > len(base):
            return None
        base = base[: len(base) - (node.level - 1)]
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base) if base else None


def _imported_names(tree: ast.AST, module: str, *, is_package: bool) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, module, is_package=is_package)
            if base is None:
                continue
            names.extend(
                base if alias.name == "*" else f"{base}.{alias.name}" for alias in node.names
            )
    return names


def _longest_unit_prefix(name: str, ids: frozenset[str]) -> str | None:
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in ids:
            return candidate
    return None


def extract(
    source_root: Path,
    *,
    package: str | None = None,
    include_tests: bool = False,
    exclude: Sequence[str] = (),
) -> dict[str, Json]:
    candidates = [
        rel
        for rel in _find_files(source_root)
        if (include_tests or not _is_test_path(rel))
        and not any(fnmatch.fnmatch(rel, glob) for glob in exclude)
        and _module_id(rel)
    ]
    root_package = _root_package(
        source_root, package, [r for r in candidates if not _is_test_path(r)]
    )

    skipped: list[tuple[str, str]] = []
    units: dict[str, dict[str, Json]] = {}
    trees: dict[str, tuple[ast.Module, bool]] = {}
    for rel in candidates:
        path = (source_root / rel).as_posix()
        try:
            text = (source_root / rel).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            skipped.append((path, "not UTF-8"))
            continue
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError):
            skipped.append((path, "syntax error"))
            continue
        module = _module_id(rel)
        units[module] = {
            "id": module,
            "path": path,
            "group": _group(rel, module, root_package),
            "loc": _loc(text),
            "layer_hint": _layer_hint(rel, module, root_package),
            "types": [],
            "escapes": {},
            "framework_refs": [],
        }
        trees[module] = (tree, rel.endswith("/__init__.py") or rel == "__init__.py")

    ids = frozenset(units)
    counts: dict[tuple[str, str], int] = {}
    for module, (tree, is_package) in trees.items():
        for name in _imported_names(tree, module, is_package=is_package):
            target = _longest_unit_prefix(name, ids)
            if target is not None and target != module:
                counts[(module, target)] = counts.get((module, target), 0) + 1

    return {
        "schema": MODEL_SCHEMA,
        "language": "python",
        "root": source_root.as_posix(),
        "capabilities": list(CAPABILITIES_DECLARED),
        "units": [units[i] for i in sorted(units)],
        "edges": [{"from": s, "to": t, "count": c} for (s, t), c in sorted(counts.items())],
        "skipped": [{"path": p, "reason": r} for p, r in sorted(skipped)],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python.py", description="Extract the neutral model from a Python source tree."
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
