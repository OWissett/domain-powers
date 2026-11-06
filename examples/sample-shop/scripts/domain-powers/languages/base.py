"""Shared types for language packs: findings, the pack protocol and the justification rule."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ALLOW_RE = re.compile(r"domain-powers:\s*allow\s+\S")
LAYERS = ("domain", "application", "infrastructure")
BOUNDARY_CODES = frozenset({"DOMAIN-DEP", "LAYER", "CROSS-CTX"})
DOMAIN_REJECTS_ALLOW = " (allow-justifications are not accepted in the domain layer)"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.code}] {self.message}"


class LanguagePack(Protocol):
    """One language's rules for the guard. Packs load their own project config."""

    @property
    def name(self) -> str: ...

    @property
    def suffixes(self) -> tuple[str, ...]: ...

    def analyse(self, path: Path, source: str) -> list[Finding]:
        """Every finding for the whole file, justifications already applied."""
        ...

    def expand_changed(self, source: str, lines: set[int]) -> set[int]:
        """Add the lines a finding is reported on when an edit touched a multi-line item."""
        ...


def justify(findings: list[Finding], source: str, *, in_domain: bool) -> list[Finding]:
    """Drop findings whose line carries an allow-justification, except in a domain layer.

    In a domain layer the justification is rejected and says so in the message.
    """
    lines = source.splitlines()
    kept: list[Finding] = []
    for f in findings:
        text = lines[f.line - 1] if 0 < f.line <= len(lines) else ""
        if not ALLOW_RE.search(text):
            kept.append(f)
        elif in_domain:
            message = f.message
            if f.code not in BOUNDARY_CODES:
                message += DOMAIN_REJECTS_ALLOW
            kept.append(Finding(f.path, f.line, f.code, message))
    return kept


def escape_counts(findings: list[Finding]) -> dict[str, int]:
    """Count findings by code, for an extractor's `escapes` field."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    return dict(sorted(counts.items()))
