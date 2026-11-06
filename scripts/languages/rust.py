"""Rust language pack (filled in by the next task)."""

from __future__ import annotations

from pathlib import Path

from languages.base import Finding


class RustPack:
    name = "rust"
    suffixes = (".rs",)

    def analyse(self, path: Path, source: str) -> list[Finding]:
        return []

    def expand_changed(self, source: str, lines: set[int]) -> set[int]:
        return lines


PACK = RustPack()
