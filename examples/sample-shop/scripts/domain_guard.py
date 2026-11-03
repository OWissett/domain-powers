#!/usr/bin/env python3
"""domain-powers edit guard.

Two modes:
  * Hook mode (default): reads a Claude Code PostToolUse JSON payload on stdin.
    Checks only the lines the Edit/Write just introduced. On violations, prints
    them to stderr and exits 2 so the agent sees them immediately.
  * Scan mode: ``domain_guard.py --scan PATH [PATH ...]`` checks whole files
    (for the quality gate / CI). Exits 1 on violations.

Checks:
  ANY          typing.Any used
  CAST         typing.cast() used
  IGNORE       type-checker suppression (# type: ignore / # pyright: ignore / mypy: ignore-errors)
  UNTYPED      function missing parameter or return annotations
  DOMAIN-DEP   domain layer imports a framework/IO library or a non-domain module
  LAYER        application layer imports infrastructure
  CROSS-CTX    a context imports another context's internals instead of its public api
  TERM         (Markdown) a word listed under Avoid in docs/language.md or the domain glossary

Suppress (outside domain layers only) with an inline justification on the same line:
    # domain-powers: allow <reason>

Configuration: [tool.domain-powers] in the nearest pyproject.toml. Stdlib only.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize
import tomllib as _toml  # Python 3.11+
from dataclasses import dataclass, field
from pathlib import Path

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
LAYERS = ("domain", "application", "infrastructure")
CTX, LAYER = 1, 2  # positions in "<root>.<context>.<layer>"


def seg(parts: list[str], i: int) -> str | None:
    """Return the i-th dotted segment, or None if the module path is shorter."""
    return parts[i] if len(parts) > i else None


ALLOW_RE = re.compile(r"domain-powers:\s*allow\s+\S")
IGNORE_RE = re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|mypy:\s*ignore-errors)(\[[^\]]*\])?")


@dataclass(frozen=True)
class Config:
    project_root: Path | None = None
    root_package: str | None = None
    source_root: Path | None = None
    contexts: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    public_module: str = "api"
    domain_forbidden: tuple[str, ...] = DEFAULT_DOMAIN_FORBIDDEN


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.code}] {self.message}"


@dataclass
class Location:
    module: str | None = None
    context: str | None = None
    layer: str | None = None
    is_test: bool = False
    is_package: bool = False


@dataclass
class FileReport:
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------- config


def load_config(start: Path) -> Config:
    for directory in [start, *start.parents]:
        candidate = directory / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            data = _toml.loads(candidate.read_text(encoding="utf-8"))
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


def locate(path: Path, cfg: Config) -> Location:
    loc = Location()
    parts = path.parts
    loc.is_test = (
        "tests" in parts
        or "test" in parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
    )
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


# ---------------------------------------------------------------- analysis


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


def check_types(path: Path, source: str, tree: ast.AST, loc: Location) -> list[Finding]:
    findings: list[Finding] = []
    lines = source.splitlines()

    def line_text(n: int) -> str:
        return lines[n - 1] if 0 < n <= len(lines) else ""

    any_lines: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and node.id == "Any") or (
            isinstance(node, ast.Attribute)
            and node.attr == "Any"
            and isinstance(node.value, ast.Name)
            and node.value.id in ("typing", "t", "typing_extensions")
        ):
            any_lines.add(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module in (
            "typing",
            "typing_extensions",
        ):
            if any(a.name == "Any" for a in node.names):
                any_lines.add(node.lineno)
        elif isinstance(node, ast.Call):
            fn = node.func
            is_cast = (isinstance(fn, ast.Name) and fn.id == "cast") or (
                isinstance(fn, ast.Attribute)
                and fn.attr == "cast"
                and isinstance(fn.value, ast.Name)
                and fn.value.id in ("typing", "t")
            )
            if is_cast:
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "CAST",
                        "cast() asks the checker to take your word for it. Narrow with "
                        "isinstance/match "
                        "or parse into a precise type instead.",
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not loc.is_test:
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if node.args.vararg:
                args.append(node.args.vararg)
            if node.args.kwarg:
                args.append(node.args.kwarg)
            missing = [a.arg for a in args if a.annotation is None and a.arg not in ("self", "cls")]
            if node.returns is None or missing:
                what = []
                if missing:
                    what.append("params " + ", ".join(missing))
                if node.returns is None:
                    what.append("return")
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "UNTYPED",
                        f"'{node.name}' is missing annotations ({'; '.join(what)}). "
                        "Untyped defs are Any.",
                    )
                )

    for n in sorted(any_lines):
        findings.append(
            Finding(
                path,
                n,
                "ANY",
                "Any switches the checker off. Use a precise type, a Protocol, a TypeVar, "
                "or object + narrowing.",
            )
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

    # Apply justifications (never honoured in domain layers).
    kept: list[Finding] = []
    for f in findings:
        justified = bool(ALLOW_RE.search(line_text(f.line)))
        if justified and loc.layer != "domain":
            continue
        if justified and loc.layer == "domain":
            f = Finding(
                f.path,
                f.line,
                f.code,
                f.message + " (allow-justifications are not accepted in the domain layer)",
            )
        kept.append(f)

    if loc.is_test:  # tests: only suppression comments matter
        kept = [f for f in kept if f.code == "IGNORE"]
    return kept


def analyse(path: Path, source: str, cfg: Config) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # mid-edit; the type checker / tests will report it
    loc = locate(path, cfg)
    findings = check_types(path, source, tree, loc) + check_imports(path, tree, loc, cfg)
    # Import findings honour the same justification rule.
    lines = source.splitlines()
    out = []
    for f in findings:
        if f.code in ("DOMAIN-DEP", "LAYER", "CROSS-CTX") and loc.layer != "domain":
            text = lines[f.line - 1] if 0 < f.line <= len(lines) else ""
            if ALLOW_RE.search(text):
                continue
        out.append(f)
    return sorted(set(out), key=lambda f: (f.line, f.code))


# ---------------------------------------------------------------- documentation language

LANGUAGE_FILE = Path("docs") / "language.md"
GLOSSARY_FILE = Path("docs") / "domain" / "glossary.md"
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
URL_RE = re.compile(r"\]\([^)]*\)|https?://\S+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
AVOID_BULLET_RE = re.compile(r"^\s*[-*]\s+\*\*Avoid:?\*\*:?\s*(.+)$", re.IGNORECASE)
TERM_HEADING_LEVEL = 3


@dataclass(frozen=True)
class Vocabulary:
    sources: tuple[Path, ...] = ()
    avoid: tuple[tuple[str, str, str, re.Pattern[str]], ...] = ()  # word, canonical, source, re
    allowed: tuple[str, ...] = ()


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    body = r"[\s-]+".join(re.escape(w) for w in phrase.split())
    return re.compile(rf"(?<![\w-]){body}(?:e?s)?(?![\w-])", re.IGNORECASE)


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _split_terms(cell: str) -> list[str]:
    return [t.strip().strip("`").strip() for t in cell.split(",") if t.strip().strip("`").strip()]


def parse_vocabulary(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(avoided word, canonical term)], [allowed phrases]) from a vocabulary file."""
    pairs: list[tuple[str, str]] = []
    allowed: list[str] = []
    header: list[str] | None = None
    section = ""
    term_heading = ""
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            header = None
            title = heading.group(2).strip()
            if len(heading.group(1)) <= TERM_HEADING_LEVEL - 1:
                section = title.lower()
            if len(heading.group(1)) == TERM_HEADING_LEVEL:
                term_heading = title
            continue
        if section.startswith("allowed phrases"):
            item = re.match(r"^\s*[-*]\s+(.+)$", line)
            if item:
                allowed.extend(_split_terms(item.group(1)))
            continue
        bullet = AVOID_BULLET_RE.match(line)
        if bullet and term_heading:
            pairs.extend((w, term_heading) for w in _split_terms(bullet.group(1)))
            continue
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = _cells(line)
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if "term" in header and "avoid" in header and len(cells) == len(header):
            canonical = cells[header.index("term")].strip("`")
            pairs.extend((w, canonical) for w in _split_terms(cells[header.index("avoid")]))
    return pairs, allowed


def load_vocabulary(start: Path) -> Vocabulary:
    for directory in [start, *start.parents]:
        files = [directory / f for f in (LANGUAGE_FILE, GLOSSARY_FILE)]
        present = [f for f in files if f.is_file()]
        if not present:
            continue
        avoid: list[tuple[str, str, str, re.Pattern[str]]] = []
        allowed: list[str] = []
        for f in present:
            try:
                pairs, allow = parse_vocabulary(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            source = f.relative_to(directory).as_posix()
            avoid.extend((w, c, source, _phrase_pattern(w)) for w, c in pairs)
            allowed.extend(allow)
            allowed.extend(c for _, c in pairs)  # canonical terms are never drift
        return Vocabulary(tuple(present), tuple(avoid), tuple(allowed))
    return Vocabulary()


def _mask(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def check_markdown(path: Path, source: str, vocab: Vocabulary) -> list[Finding]:
    if not vocab.avoid or path.resolve() in {p.resolve() for p in vocab.sources}:
        return []
    if parse_vocabulary(source)[0]:
        return []  # a file that defines vocabulary necessarily names the avoided words
    allowed = [_phrase_pattern(a) for a in vocab.allowed]
    findings: list[Finding] = []
    in_fence = False
    for n, raw in enumerate(source.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or ALLOW_RE.search(raw):
            continue
        line = _mask(_mask(raw, INLINE_CODE_RE), URL_RE)
        for pattern in allowed:
            line = _mask(line, pattern)
        for word, canonical, source_file, pattern in vocab.avoid:
            m = pattern.search(line)
            if m:
                findings.append(
                    Finding(
                        path,
                        n,
                        "TERM",
                        f"'{m.group(0)}' is an avoided synonym ('{word}'): use "
                        f"'{canonical}' as defined in {source_file}. If this really is a "
                        "different concept, define it there first.",
                    )
                )
    return findings


# ---------------------------------------------------------------- hook mode


def changed_lines(source: str, payload: dict[str, object]) -> set[int] | None:
    """Return line numbers introduced by the tool call, or None for 'whole file'."""
    tool = payload.get("tool_name")
    tin = payload.get("tool_input")
    if not isinstance(tin, dict):
        return None
    if tool == "Write":
        return None
    snippets: list[str] = []
    if tool == "Edit" and isinstance(tin.get("new_string"), str):
        snippets.append(tin["new_string"])
    elif tool == "MultiEdit" and isinstance(tin.get("edits"), list):
        snippets.extend(
            e["new_string"]
            for e in tin["edits"]
            if isinstance(e, dict) and isinstance(e.get("new_string"), str)
        )
    if not snippets:
        return None
    result: set[int] = set()
    for snippet in snippets:
        if not snippet.strip():
            continue
        idx = source.find(snippet)
        if idx < 0:
            return None  # file changed since; be conservative and check everything
        start = source.count("\n", 0, idx) + 1
        result.update(range(start, start + snippet.count("\n") + 1))
    return result


def hook_main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    tin = payload.get("tool_input")
    if not isinstance(tin, dict):
        return 0
    raw_path = tin.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.endswith((".py", ".pyi", ".md")):
        return 0
    path = Path(raw_path)
    if not path.is_absolute() and isinstance(payload.get("cwd"), str):
        path = Path(str(payload["cwd"])) / path
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    is_markdown = path.suffix == ".md"
    if is_markdown:
        findings = check_markdown(path, source, load_vocabulary(path.parent.resolve()))
    else:
        findings = analyse(path, source, load_config(path.parent))
    lines = changed_lines(source, payload)
    if lines is not None:
        findings = [f for f in findings if f.line in lines]
    if not findings:
        return 0
    if is_markdown:
        print(
            "domain-powers guard: the edit you just made drifts from the documented language.",
            file=sys.stderr,
        )
        for f in findings:
            print("  " + f.render(), file=sys.stderr)
        print("See domain-powers:defining-documentation-language.", file=sys.stderr)
        return 2
    print(
        "domain-powers guard: the edit you just made weakens a guarantee.",
        file=sys.stderr,
    )
    for f in findings:
        print("  " + f.render(), file=sys.stderr)
    print(
        "Fix the design (see domain-powers:type-driven-design / designing-boundaries). "
        "Outside domain layers, a deliberate exception needs '# domain-powers: allow <reason>' "
        "on the same line.",
        file=sys.stderr,
    )
    return 2


# ---------------------------------------------------------------- scan mode


def scan_main(targets: list[str]) -> int:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
            files.extend(sorted(p.rglob("*.md")))
        elif p.suffix in (".py", ".pyi", ".md"):
            files.append(p)
    total: list[Finding] = []
    cfg_cache: dict[Path, Config] = {}
    vocab_cache: dict[Path, Vocabulary] = {}
    for f in files:
        try:
            source = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if f.suffix == ".md":
            vocab = vocab_cache.setdefault(f.parent, load_vocabulary(f.parent.resolve()))
            total.extend(check_markdown(f, source, vocab))
        else:
            cfg = cfg_cache.setdefault(f.parent, load_config(f.parent.resolve()))
            total.extend(analyse(f, source, cfg))
    for finding in total:
        print(finding.render())
    counts: dict[str, int] = {}
    for finding in total:
        counts[finding.code] = counts.get(finding.code, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"domain-powers scan: {len(files)} files, {len(total)} findings ({summary})")
    return 1 if total else 0


def main(argv: list[str]) -> int:
    if seg(argv, 1) == "--scan":
        return scan_main(argv[2:] or ["src"])
    return hook_main()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
