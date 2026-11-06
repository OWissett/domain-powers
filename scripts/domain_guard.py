#!/usr/bin/env python3
"""domain-powers edit guard.

Two modes:
  * Hook mode (default): reads a Claude Code or Codex PostToolUse JSON payload on stdin.
    Checks lines introduced by Edit/Write or apply_patch. On violations, prints
    them to stderr and exits 2 so the agent sees them immediately.
  * Scan mode: ``domain_guard.py --scan PATH [PATH ...]`` checks whole files
    (for the quality gate / CI). Exits 1 on violations.

This file is language-agnostic. Source files go to the language pack that owns their
suffix (``languages/<name>.py``); each pack reports type escapes and boundary findings
with the shared codes:
  ANY, CAST, IGNORE   type escapes common to most languages (UNTYPED, UNSAFE, PANIC are
                      language-specific; see each pack)
  DOMAIN-DEP          domain layer depends on a framework/IO library or a non-domain module
  LAYER               application layer depends on its own infrastructure
  CROSS-CTX           a context reaches another context's internals instead of its public api
Markdown is checked here:
  TERM                a word listed under Avoid in docs/language.md or the domain glossary

Suppress (outside domain layers only) with an inline justification on the same line:
    domain-powers: allow <reason>     (in the language's comment syntax)

Stdlib only. Run from anywhere: the packs are found next to this file.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from languages import SOURCE_SUFFIXES, pack_for
from languages.base import ALLOW_RE, Finding

MARKDOWN_SUFFIXES = (".md",)
CHECKED_SUFFIXES = SOURCE_SUFFIXES + MARKDOWN_SUFFIXES
SKIP_DIRS = frozenset({".git", "target", "node_modules", ".venv", "venv", "__pycache__"})


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


@dataclass
class PatchEdit:
    path: str
    snippets: list[str] | None


def patch_edits(command: str) -> list[PatchEdit]:
    """Read changed paths and added blocks from an already-applied Codex patch."""
    edits: list[PatchEdit] = []
    current: PatchEdit | None = None
    block: list[str] = []

    def flush() -> None:
        if current is not None and current.snippets is not None and block:
            current.snippets.append("\n".join(block))
        block.clear()

    for line in command.splitlines():
        if line.startswith("*** ") or line.startswith("@@"):
            flush()
        if line.startswith("*** Add File: "):
            current = PatchEdit(line.removeprefix("*** Add File: "), None)
            edits.append(current)
        elif line.startswith("*** Update File: "):
            current = PatchEdit(line.removeprefix("*** Update File: "), [])
            edits.append(current)
        elif line.startswith("*** Move to: ") and current is not None:
            current.path = line.removeprefix("*** Move to: ")
            current.snippets = None  # moving into a domain can change every import's validity
        elif line.startswith(("*** Delete File: ", "*** End Patch")):
            current = None
        elif line.startswith("+") and current is not None:
            block.append(line[1:])
        else:
            flush()
    flush()
    return edits


def snippet_lines(source: str, snippets: list[str]) -> set[int] | None:
    """Locate added blocks, checking the whole file if their location is ambiguous."""
    result: set[int] = set()
    for snippet in snippets:
        if not snippet.strip():
            continue
        idx = source.find(snippet)
        if idx < 0 or source.find(snippet, idx + 1) >= 0:
            return None
        start = source.count("\n", 0, idx) + 1
        result.update(range(start, start + snippet.count("\n") + 1))
    return result


def edit_snippets(payload: dict[str, object]) -> list[str] | None:
    """New text from a Claude Edit/MultiEdit payload, or None for 'whole file'."""
    tool = payload.get("tool_name")
    tin = payload.get("tool_input")
    if not isinstance(tin, dict) or tool == "Write":
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
    return snippets or None


_vocabulary = lru_cache(maxsize=256)(load_vocabulary)


def analyse_file(path: Path, source: str) -> list[Finding]:
    """Every finding for one file, by its suffix."""
    if path.suffix in MARKDOWN_SUFFIXES:
        return check_markdown(path, source, _vocabulary(path.parent.resolve()))
    pack = pack_for(path)
    return [] if pack is None else pack.analyse(path, source)


def inspect_file(path: Path, snippets: list[str] | None) -> list[Finding]:
    """Findings on the lines an edit introduced (all lines when snippets is None)."""
    if path.suffix not in CHECKED_SUFFIXES:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    findings = analyse_file(path, source)
    lines = None if snippets is None else snippet_lines(source, snippets)
    pack = pack_for(path)
    if lines is not None and pack is not None:
        lines = pack.expand_changed(source, lines)
    return findings if lines is None else [f for f in findings if f.line in lines]


def _resolve(raw: str, payload: dict[str, object]) -> Path:
    path = Path(raw)
    if not path.is_absolute() and isinstance(payload.get("cwd"), str):
        path = Path(str(payload["cwd"])) / path
    return path


def _report(findings: list[Finding], *, markdown: bool) -> None:
    if markdown:
        print(
            "domain-powers guard: the edit you just made drifts from the documented language.",
            file=sys.stderr,
        )
        for f in findings:
            print("  " + f.render(), file=sys.stderr)
        print("See domain-powers:defining-documentation-language.", file=sys.stderr)
        return
    print("domain-powers guard: the edit you just made weakens a guarantee.", file=sys.stderr)
    for f in findings:
        print("  " + f.render(), file=sys.stderr)
    print(
        "Fix the design (see domain-powers:type-driven-design / designing-boundaries). "
        "Outside domain layers, a deliberate exception needs 'domain-powers: allow <reason>' "
        "in a comment on the same line.",
        file=sys.stderr,
    )


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
    if payload.get("tool_name") == "apply_patch":
        command = tin.get("command")
        if not isinstance(command, str):
            return 0
        findings: list[Finding] = []
        for edit in patch_edits(command):
            findings.extend(inspect_file(_resolve(edit.path, payload), edit.snippets))
        if not findings:
            return 0
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        print(
            "domain-powers guard: fix these findings before continuing. "
            "Use the paired domain-powers skill for the reported rule.",
            file=sys.stderr,
        )
        return 2
    raw_path = tin.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.endswith(CHECKED_SUFFIXES):
        return 0
    path = _resolve(raw_path, payload)
    findings = inspect_file(path, edit_snippets(payload))
    if not findings:
        return 0
    _report(findings, markdown=path.suffix in MARKDOWN_SUFFIXES)
    return 2


# ---------------------------------------------------------------- scan mode


def _walk(directory: Path) -> list[Path]:
    found: list[Path] = []
    for p in sorted(directory.rglob("*")):
        rel = p.relative_to(directory).parts
        if any(part in SKIP_DIRS for part in rel[:-1]):
            continue
        if p.is_file() and p.suffix in CHECKED_SUFFIXES and p.suffix != ".pyi":
            found.append(p)
    return found


def scan_main(targets: list[str]) -> int:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(_walk(p))
        elif p.suffix in CHECKED_SUFFIXES:
            files.append(p)
    total: list[Finding] = []
    for f in files:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        total.extend(analyse_file(f, source))
    for finding in total:
        print(finding.render())
    counts: dict[str, int] = {}
    for finding in total:
        counts[finding.code] = counts.get(finding.code, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"domain-powers scan: {len(files)} files, {len(total)} findings ({summary})")
    return 1 if total else 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--scan":
        return scan_main(argv[2:] or ["src"])
    return hook_main()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
