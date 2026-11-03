"""Language-agnostic migration assessment core.

Commands (added in later tasks):
    core.py analyse model.json [--target target.toml] [--churn]
    core.py compare assessment.json baseline.json

The core never parses source code. Extractors write a neutral model
(``domain-powers.assess.model/1``) and the core only reads that JSON.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# --- Model ------------------------------------------------------------------------------------

MODEL_SCHEMA = "domain-powers.assess.model/1"
RESULT_SCHEMA = "domain-powers.assess.result/1"

CAPABILITIES: frozenset[str] = frozenset(
    {"edges", "types", "data_only", "escapes", "framework_refs", "layer_hints"}
)

HINTS: tuple[str, ...] = (
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
)
MODEL_LIKE: frozenset[str] = frozenset({"models", "entities", "schemas", "domain"})
SERVICE_LIKE: frozenset[str] = frozenset({"services", "managers", "handlers", "application"})
EDGE: frozenset[str] = frozenset(
    {
        "views",
        "controllers",
        "routes",
        "api",
        "serializers",
        "forms",
        "adapters",
        "infrastructure",
        "repositories",
        "dao",
        "tasks",
    }
)
SHARED: frozenset[str] = frozenset({"utils", "helpers", "common", "core"})

Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]

# Metric key (the name of the Assessment field it fills) -> reason it is not applicable.
NotApplicable = dict[str, str]


class ModelError(Exception):
    """The model file is unreadable or does not follow the schema."""


@dataclass(frozen=True)
class TypeDecl:
    name: str
    data_only: bool | None


@dataclass(frozen=True)
class Unit:
    id: str
    path: str
    group: str
    loc: int
    layer_hint: str | None
    types: tuple[TypeDecl, ...]
    escapes: dict[str, int]
    framework_refs: tuple[str, ...]


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    count: int


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: str


@dataclass(frozen=True)
class Model:
    language: str
    root: str
    capabilities: frozenset[str]
    units: tuple[Unit, ...]
    edges: tuple[Edge, ...]
    skipped: tuple[Skipped, ...]

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


def _obj(raw: object, where: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ModelError(f"{where}: expected an object")
    out: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ModelError(f"{where}: keys must be strings")
        out[key] = value
    return out


def _list(raw: object, where: str) -> list[object]:
    if not isinstance(raw, list):
        raise ModelError(f"{where}: expected a list")
    return list(raw)


def _str(raw: object, where: str) -> str:
    if not isinstance(raw, str):
        raise ModelError(f"{where}: expected a string")
    return raw


def _int(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ModelError(f"{where}: expected an integer")
    return raw


def _type_decl(raw: object, where: str) -> TypeDecl:
    obj = _obj(raw, where)
    data_only = obj.get("data_only")
    if data_only is not None and not isinstance(data_only, bool):
        raise ModelError(f"{where}.data_only: expected a boolean or null")
    return TypeDecl(_str(obj.get("name"), f"{where}.name"), data_only)


def _unit(raw: object, where: str) -> Unit:
    obj = _obj(raw, where)
    hint = obj.get("layer_hint")
    if hint is not None:
        hint = _str(hint, f"{where}.layer_hint")
    escapes_raw = _obj(obj.get("escapes", {}), f"{where}.escapes")
    return Unit(
        id=_str(obj.get("id"), f"{where}.id"),
        path=_str(obj.get("path"), f"{where}.path"),
        group=_str(obj.get("group"), f"{where}.group"),
        loc=_int(obj.get("loc"), f"{where}.loc"),
        layer_hint=hint,
        types=tuple(
            _type_decl(t, f"{where}.types[{i}]")
            for i, t in enumerate(_list(obj.get("types", []), f"{where}.types"))
        ),
        escapes={k: _int(v, f"{where}.escapes.{k}") for k, v in sorted(escapes_raw.items())},
        framework_refs=tuple(
            _str(r, f"{where}.framework_refs")
            for r in _list(obj.get("framework_refs", []), f"{where}.framework_refs")
        ),
    )


def _edge(raw: object, where: str) -> Edge:
    obj = _obj(raw, where)
    return Edge(
        source=_str(obj.get("from"), f"{where}.from"),
        target=_str(obj.get("to"), f"{where}.to"),
        count=_int(obj.get("count"), f"{where}.count"),
    )


def _skipped(raw: object, where: str) -> Skipped:
    obj = _obj(raw, where)
    return Skipped(
        _str(obj.get("path"), f"{where}.path"), _str(obj.get("reason"), f"{where}.reason")
    )


def parse_model(raw: object) -> Model:
    """Validate a decoded model document and return it with units and edges sorted."""
    top = _obj(raw, "model")
    if top.get("schema") != MODEL_SCHEMA:
        raise ModelError(f"unsupported schema {top.get('schema')!r}, expected {MODEL_SCHEMA}")
    capabilities = frozenset(
        _str(c, "capabilities") for c in _list(top.get("capabilities", []), "capabilities")
    )
    unknown = sorted(capabilities - CAPABILITIES)
    if unknown:
        raise ModelError(f"unknown capabilities: {', '.join(unknown)}")
    units = sorted(
        (_unit(u, f"units[{i}]") for i, u in enumerate(_list(top.get("units", []), "units"))),
        key=lambda u: u.id,
    )
    ids: set[str] = set()
    for u in units:
        if u.id in ids:
            raise ModelError(f"duplicate unit id: {u.id}")
        ids.add(u.id)
    edges = sorted(
        (_edge(e, f"edges[{i}]") for i, e in enumerate(_list(top.get("edges", []), "edges"))),
        key=lambda e: (e.source, e.target),
    )
    for e in edges:
        for end in (e.source, e.target):
            if end not in ids:
                raise ModelError(f"edge references unknown unit: {end}")
    skipped = tuple(
        _skipped(s, f"skipped[{i}]") for i, s in enumerate(_list(top.get("skipped", []), "skipped"))
    )
    return Model(
        language=_str(top.get("language"), "language"),
        root=_str(top.get("root"), "root"),
        capabilities=capabilities,
        units=tuple(units),
        edges=tuple(edges),
        skipped=skipped,
    )


def load_model(path: Path) -> Model:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ModelError(f"cannot read {path}: {exc}") from exc
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError(f"{path} is not valid JSON: {exc}") from exc
    return parse_model(raw)


def require(model: Model, na: NotApplicable, metric: str, *capabilities: str) -> bool:
    """Return True if the model has every capability, else record why `metric` is not applicable."""
    for capability in capabilities:
        if not model.has(capability):
            na[metric] = f"missing capability: {capability}"
            return False
    return True


# --- Shape ------------------------------------------------------------------------------------

LAYERING_NEUTRAL: frozenset[str] = frozenset(
    {"domain", "application", "infrastructure", "adapters", "tests"}
)
HUB_LIMIT = 10
MIN_FEATURE_GROUPS = 2
MIN_GROUPS = 2
NUMSTAT_FIELDS = 3


def strongly_connected(nodes: Sequence[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Iterative Tarjan. Returns components of more than one node, each sorted, the list sorted."""
    known = set(nodes)
    succ: dict[str, list[str]] = {n: [] for n in known}
    for source, target in edges:
        if source in known and target in known:
            succ[source].append(target)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    for root in sorted(known):
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, pos = work.pop()
            if pos < len(succ[node]):
                work.append((node, pos + 1))
                nxt = succ[node][pos]
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(sorted(component))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return sorted(found)


def layout_style(model: Model, na: NotApplicable) -> str | None:
    if not require(model, na, "layout", "layer_hints"):
        return None
    total = len(model.units)
    by_group: dict[str, list[Unit]] = {}
    for u in model.units:
        by_group.setdefault(u.group, []).append(u)
    feature_groups = [
        members
        for members in by_group.values()
        if {u.layer_hint for u in members} & MODEL_LIKE
        and {u.layer_hint for u in members} & SERVICE_LIKE
        and {u.layer_hint for u in members} & EDGE
    ]
    if (
        len(feature_groups) >= MIN_FEATURE_GROUPS
        and sum(len(g) for g in feature_groups) * 2 >= total
    ):
        return "feature packages"
    technical = sum(
        1 for u in model.units if u.layer_hint is not None and u.layer_hint not in LAYERING_NEUTRAL
    )
    if total and technical * 2 >= total:
        return "technical layering"
    return "mixed"


def unit_cycles(model: Model, na: NotApplicable) -> list[list[str]] | None:
    if not require(model, na, "unit_cycles", "edges"):
        return None
    return strongly_connected(
        [u.id for u in model.units], [(e.source, e.target) for e in model.edges]
    )


def _group_edges(model: Model) -> set[tuple[str, str]]:
    group_of = {u.id: u.group for u in model.units}
    pairs: set[tuple[str, str]] = set()
    for e in model.edges:
        src, dst = group_of.get(e.source), group_of.get(e.target)
        if src is not None and dst is not None and src != dst:
            pairs.add((src, dst))
    return pairs


def _group_applicable(model: Model, na: NotApplicable, metric: str) -> bool:
    if not require(model, na, metric, "edges"):
        return False
    if len({u.group for u in model.units}) < MIN_GROUPS:
        na[metric] = "fewer than two groups"
        return False
    if not _group_edges(model):
        na[metric] = "no internal edges"
        return False
    return True


def group_cycles(model: Model, na: NotApplicable) -> list[list[str]] | None:
    if not _group_applicable(model, na, "group_cycles"):
        return None
    return strongly_connected(sorted({u.group for u in model.units}), _group_edges(model))


@dataclass(frozen=True)
class Hub:
    id: str
    fan_in: int


def hubs(model: Model, na: NotApplicable) -> list[Hub] | None:
    if not require(model, na, "hubs", "edges"):
        return None
    importers: dict[str, set[str]] = {}
    for e in model.edges:
        importers.setdefault(e.target, set()).add(e.source)
    ranked = sorted((Hub(t, len(s)) for t, s in importers.items()), key=lambda h: (-h.fan_in, h.id))
    return ranked[:HUB_LIMIT]


@dataclass(frozen=True)
class GroupCoupling:
    group: str
    ca: int
    ce: int
    instability: float | None


def coupling(model: Model, na: NotApplicable) -> list[GroupCoupling] | None:
    if not _group_applicable(model, na, "coupling"):
        return None
    group_of = {u.id: u.group for u in model.units}
    afferent: dict[str, set[str]] = {g: set() for g in group_of.values()}
    efferent: dict[str, set[str]] = {g: set() for g in group_of.values()}
    for e in model.edges:
        src, dst = group_of.get(e.source), group_of.get(e.target)
        if src is None or dst is None or src == dst:
            continue
        afferent[dst].add(e.source)
        efferent[src].add(e.target)
    result: list[GroupCoupling] = []
    for g in sorted(afferent):
        ca, ce = len(afferent[g]), len(efferent[g])
        result.append(GroupCoupling(g, ca, ce, ce / (ca + ce) if ca + ce else None))
    return result


def parse_numstat(text: str) -> dict[str, int]:
    """Sum added + deleted lines per path; binary and rename lines are skipped."""
    totals: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split("\t", NUMSTAT_FIELDS - 1)
        if len(parts) != NUMSTAT_FIELDS:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-" or "=>" in path:
            continue
        try:
            totals[path] = totals.get(path, 0) + int(added) + int(deleted)
        except ValueError:
            continue
    return totals


@dataclass(frozen=True)
class UnitChurn:
    id: str
    lines: int


def churn(model: Model, cwd: Path, na: NotApplicable) -> list[UnitChurn] | None:
    command = [
        "git",
        "-C",
        str(cwd),
        "log",
        "--numstat",
        "--format=",
        "--relative",
        "--since=12.months.ago",
    ]
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    except FileNotFoundError:
        na["churn"] = "git unavailable"
        return None
    if done.returncode != 0:
        na["churn"] = "not a git repository"
        return None
    totals = parse_numstat(done.stdout)
    if not any(u.path in totals for u in model.units):
        na["churn"] = "no git paths matched units"
        return None
    ranked = [UnitChurn(u.id, totals[u.path]) for u in model.units if totals.get(u.path, 0) > 0]
    return sorted(ranked, key=lambda c: (-c.lines, c.id))
