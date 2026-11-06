"""Python language pack: type escapes and boundary rules for `.py` and `.pyi` files.

Configuration: [tool.domain-powers] in the nearest pyproject.toml.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from languages.base import LAYERS, Finding, justify

DEFAULT_DOMAIN_FORBIDDEN = (
    "sqlalchemy",
    "django",
    "fastapi",
    "flask",
    "starlette",
    "pydantic",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "boto3",
    "botocore",
    "redis",
    "celery",
    "kombu",
    "psycopg",
    "psycopg2",
    "pymongo",
    "motor",
    "sqlmodel",
    "peewee",
    "tortoise",
    "marshmallow",
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
)
CTX, LAYER = 1, 2  # positions in "<root>.<context>.<layer>"
IGNORE_RE = re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|mypy:\s*ignore-errors)(\[[^\]]*\])?")


def seg(parts: list[str], i: int) -> str | None:
    """Return the i-th dotted segment, or None if the module path is shorter."""
    return parts[i] if len(parts) > i else None


@dataclass(frozen=True)
class Config:
    project_root: Path | None = None
    root_package: str | None = None
    source_root: Path | None = None
    contexts: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    public_module: str = "api"
    domain_forbidden: tuple[str, ...] = DEFAULT_DOMAIN_FORBIDDEN


@dataclass
class Location:
    module: str | None = None
    context: str | None = None
    layer: str | None = None
    is_test: bool = False
    is_package: bool = False


# ---------------------------------------------------------------- config


@lru_cache(maxsize=256)
def load_config(start: Path) -> Config:
    for directory in [start, *start.parents]:
        candidate = directory / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            data = tomllib.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Config()
        section = data.get("tool", {}).get("domain-powers")
        if not isinstance(section, dict):
            continue  # keep walking: a nested pyproject may lack the table
        extra = tuple(str(x) for x in section.get("domain_forbidden", []))
        return Config(
            project_root=directory,
            root_package=section.get("root_package"),
            source_root=directory / str(section.get("source_root", "src")),
            contexts=tuple(str(c) for c in section.get("contexts", [])),
            shared=tuple(str(s) for s in section.get("shared", [])),
            public_module=str(section.get("public_module", "api")),
            domain_forbidden=DEFAULT_DOMAIN_FORBIDDEN + extra,
        )
    return Config()


def is_test_path(path: Path) -> bool:
    parts = path.parts
    return (
        "tests" in parts
        or "test" in parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
    )


def locate(path: Path, cfg: Config) -> Location:
    loc = Location()
    parts = path.parts
    loc.is_test = is_test_path(path)
    loc.is_package = path.name == "__init__.py"
    if cfg.source_root is not None and cfg.root_package:
        try:
            rel = path.resolve().relative_to(cfg.source_root.resolve())
        except ValueError:
            rel = None
        if rel is not None:
            mod_parts = list(rel.with_suffix("").parts)
            if mod_parts and mod_parts[-1] == "__init__":
                mod_parts = mod_parts[:-1]
            loc.module = ".".join(mod_parts)
            if mod_parts and mod_parts[0] == cfg.root_package:
                ctx = seg(mod_parts, CTX)
                if ctx in cfg.contexts:
                    loc.context = ctx
                    layer = seg(mod_parts, LAYER)
                    loc.layer = layer if layer in LAYERS else None
            return loc
    # No config (or file outside source root): infer layer from directory names.
    for layer in LAYERS:
        if layer in parts[:-1]:
            loc.layer = layer
    return loc


# ---------------------------------------------------------------- imports


def resolve_relative(node: ast.ImportFrom, loc: Location) -> str | None:
    if node.level == 0:
        return node.module
    if loc.module is None:
        return None
    base = loc.module.split(".")
    if not loc.is_package:
        base = base[:-1]
    if node.level > 1:
        base = base[: len(base) - (node.level - 1)]
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base) if base else None


def imported_modules(tree: ast.AST, loc: Location) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = resolve_relative(node, loc)
            if mod is None:
                continue
            for alias in node.names:
                # "from shop.billing import api" imports the submodule shop.billing.api
                out.append((node.lineno, f"{mod}.{alias.name}" if alias.name != "*" else mod))
    return out


def framework_refs(
    tree: ast.AST, forbidden: tuple[str, ...] = DEFAULT_DOMAIN_FORBIDDEN
) -> list[str]:
    """Top-level absolute imports that name a framework or I/O library, sorted."""
    tops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            tops.add(node.module.split(".")[0])
    return sorted(top for top in tops if top in forbidden)


def _domain_import_finding(
    path: Path, line: int, mod: str, loc: Location, cfg: Config
) -> Finding | None:
    parts = mod.split(".")
    top = parts[0]
    if top in cfg.domain_forbidden:
        return Finding(
            path,
            line,
            "DOMAIN-DEP",
            f"domain layer imports '{top}'. Keep domain pure: define a Protocol port in "
            "domain and implement it in infrastructure (domain-powers:designing-boundaries).",
        )
    if cfg.root_package is not None and top == cfg.root_package:
        target = seg(parts, CTX)
        own_domain = target == loc.context and seg(parts, LAYER) == "domain"
        if target is not None and target not in cfg.shared and not own_domain:
            shared = ", ".join(cfg.shared) or "none configured"
            return Finding(
                path,
                line,
                "DOMAIN-DEP",
                f"domain layer imports '{mod}'. Domain may import only its own "
                f"context's domain and the shared kernel ({shared}).",
            )
        return None
    if cfg.root_package is None and any(p in ("infrastructure", "application") for p in parts):
        return Finding(
            path,
            line,
            "DOMAIN-DEP",
            f"domain layer imports '{mod}' from an outer layer. Dependencies point inward.",
        )
    return None


def check_imports(path: Path, tree: ast.AST, loc: Location, cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    root = cfg.root_package
    for line, mod in imported_modules(tree, loc):
        parts = mod.split(".")
        internal = root is not None and parts[0] == root
        target = seg(parts, CTX)
        target_layer = seg(parts, LAYER)

        if loc.layer == "domain" and not loc.is_test:
            found = _domain_import_finding(path, line, mod, loc, cfg)
            if found is not None:
                findings.append(found)

        app_to_infra = (
            loc.layer == "application"
            and internal
            and target == loc.context
            and target_layer == "infrastructure"
        )
        if app_to_infra and not loc.is_test:
            findings.append(
                Finding(
                    path,
                    line,
                    "LAYER",
                    f"application imports '{mod}'. Depend on a port (Protocol); wire the "
                    "adapter in the composition root.",
                )
            )

        crosses = internal and loc.context and target in cfg.contexts and target != loc.context
        if crosses and target_layer != cfg.public_module:
            public = f"{root}.{target}.{cfg.public_module}"
            findings.append(
                Finding(
                    path,
                    line,
                    "CROSS-CTX",
                    f"context '{loc.context}' imports '{mod}'. Other contexts may only use "
                    f"'{public}' (DTOs, commands, integration events).",
                )
            )
    return findings


# ---------------------------------------------------------------- type escapes


def _is_cast(call: ast.Call) -> bool:
    fn = call.func
    return (isinstance(fn, ast.Name) and fn.id == "cast") or (
        isinstance(fn, ast.Attribute)
        and fn.attr == "cast"
        and isinstance(fn.value, ast.Name)
        and fn.value.id in ("typing", "t")
    )


def _missing_annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg:
        args.append(node.args.vararg)
    if node.args.kwarg:
        args.append(node.args.kwarg)
    what = []
    missing = [a.arg for a in args if a.annotation is None and a.arg not in ("self", "cls")]
    if missing:
        what.append("params " + ", ".join(missing))
    if node.returns is None:
        what.append("return")
    return what


def escape_findings(path: Path, source: str, tree: ast.AST, *, is_test: bool) -> list[Finding]:
    """Type-escape findings before justifications. In tests only suppressions count."""
    findings: list[Finding] = []
    any_lines: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and node.id == "Any") or (
            isinstance(node, ast.Attribute)
            and node.attr == "Any"
            and isinstance(node.value, ast.Name)
            and node.value.id in ("typing", "t", "typing_extensions")
        ):
            any_lines.add(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module in ("typing", "typing_extensions"):
            if any(a.name == "Any" for a in node.names):
                any_lines.add(node.lineno)
        elif isinstance(node, ast.Call) and _is_cast(node):
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "CAST",
                    "cast() asks the checker to take your word for it. Narrow with "
                    "isinstance/match or parse into a precise type instead.",
                )
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            what = _missing_annotations(node)
            if what:
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "UNTYPED",
                        f"'{node.name}' is missing annotations ({'; '.join(what)}). "
                        "Untyped defs are Any.",
                    )
                )
    findings.extend(
        Finding(
            path,
            n,
            "ANY",
            "Any switches the checker off. Use a precise type, a Protocol, a TypeVar, "
            "or object + narrowing.",
        )
        for n in sorted(any_lines)
    )
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type != tokenize.COMMENT:
                continue
            m = IGNORE_RE.search(tok.string)
            if not m:
                continue
            bare = m.group(2) is None and m.group(1).startswith("type")
            msg = (
                "bare suppression; at minimum it needs an error code, and a design fix is better"
                if bare
                else "type-checker suppression. Fix the design so the checker agrees"
            )
            findings.append(Finding(path, tok.start[0], "IGNORE", msg + "."))
    except (tokenize.TokenError, IndentationError):
        pass
    if is_test:
        findings = [f for f in findings if f.code == "IGNORE"]
    return findings


# ---------------------------------------------------------------- pack


class PythonPack:
    name = "python"
    suffixes = (".py", ".pyi")

    def analyse(self, path: Path, source: str) -> list[Finding]:
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return []  # mid-edit; the type checker / tests will report it
        cfg = load_config(path.parent.resolve())
        loc = locate(path, cfg)
        findings = escape_findings(path, source, tree, is_test=loc.is_test)
        findings += check_imports(path, tree, loc, cfg)
        kept = justify(findings, source, in_domain=loc.layer == "domain")
        return sorted(set(kept), key=lambda f: (f.line, f.code))

    def expand_changed(self, source: str, lines: set[int]) -> set[int]:
        """Include headers when a multiline import or function signature was edited."""
        try:
            tree = ast.parse(source)
            logical_ends = [
                token.start[0]
                for token in tokenize.generate_tokens(io.StringIO(source).readline)
                if token.type == tokenize.NEWLINE
            ]
        except (SyntaxError, tokenize.TokenError):
            return lines
        result = set(lines)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end = node.end_lineno or node.lineno
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = next((line for line in logical_ends if line >= node.lineno), node.lineno)
            else:
                continue
            if any(node.lineno <= line <= end for line in lines):
                result.add(node.lineno)
        return result


PACK = PythonPack()
