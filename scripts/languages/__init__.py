"""Language packs for the domain-powers guard and extractors.

Each pack lives in its own module and is registered here by file suffix. To add a
language, write `languages/<name>.py` exposing `PACK` and add it to `PACKS`.
"""

from __future__ import annotations

from pathlib import Path

from languages import python, rust
from languages.base import Finding, LanguagePack

PACKS: tuple[LanguagePack, ...] = (python.PACK, rust.PACK)
SOURCE_SUFFIXES: tuple[str, ...] = tuple(s for pack in PACKS for s in pack.suffixes)


def pack_for(path: Path) -> LanguagePack | None:
    """The pack that owns this file's suffix, if any."""
    for pack in PACKS:
        if path.suffix in pack.suffixes:
            return pack
    return None


__all__ = ["PACKS", "SOURCE_SUFFIXES", "Finding", "LanguagePack", "pack_for"]
