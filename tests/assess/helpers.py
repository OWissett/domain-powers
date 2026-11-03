"""Builders for neutral models and source trees used by the assessment tests."""

from collections.abc import Sequence
from pathlib import Path

import core


def unit(
    id: str,
    *,
    group: str | None = None,
    hint: str | None = None,
    types: Sequence[tuple[str, bool]] = (),
    loc: int = 10,
    escapes: dict[str, int] | None = None,
    refs: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "id": id,
        "path": id.replace(".", "/") + ".py",
        "group": group if group is not None else id.rpartition(".")[0],
        "loc": loc,
        "layer_hint": hint,
        "types": [{"name": n, "data_only": d} for n, d in types],
        "escapes": dict(escapes or {}),
        "framework_refs": list(refs),
    }


def make_model(
    units: Sequence[dict[str, object]],
    edges: Sequence[tuple[str, str, int]] = (),
    *,
    capabilities: Sequence[str] | None = None,
) -> core.Model:
    caps = sorted(core.CAPABILITIES) if capabilities is None else list(capabilities)
    raw: dict[str, object] = {
        "schema": core.MODEL_SCHEMA,
        "language": "python",
        "root": "src",
        "capabilities": caps,
        "units": list(units),
        "edges": [{"from": s, "to": t, "count": c} for s, t, c in edges],
        "skipped": [],
    }
    return core.parse_model(raw)


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
