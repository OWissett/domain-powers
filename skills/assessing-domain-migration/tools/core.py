"""Language-agnostic migration assessment core.

Commands (added in later tasks):
    core.py analyse model.json [--target target.toml] [--churn]
    core.py compare assessment.json baseline.json

The core never parses source code. Extractors write a neutral model
(``domain-powers.assess.model/1``) and the core only reads that JSON.
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import math
import re
import subprocess
import sys
import tomllib
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


# --- Target -----------------------------------------------------------------------------------

CLASSIFICATIONS: tuple[str, ...] = ("core", "supporting", "generic")


class TargetError(Exception):
    """The target file is unreadable, malformed or inconsistent with the model."""


class OverlapError(TargetError):
    def __init__(self, overlaps: dict[str, list[str]]) -> None:
        self.overlaps = overlaps
        lines = [f"{unit}: {', '.join(contexts)}" for unit, contexts in sorted(overlaps.items())]
        super().__init__("units match several contexts:\n" + "\n".join(lines))


@dataclass(frozen=True)
class Context:
    name: str
    classification: str
    units: tuple[str, ...]
    public: tuple[str, ...]


@dataclass(frozen=True)
class Target:
    contexts: tuple[Context, ...]


def _patterns(raw: object, name: str, field: str, *, required: bool) -> tuple[str, ...]:
    if raw is None and not required:
        return ()
    if not isinstance(raw, list) or (required and not raw):
        kind = "a non-empty list" if required else "a list"
        raise TargetError(f"context {name!r}: {field} must be {kind} of strings")
    items: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise TargetError(f"context {name!r}: {field} must be a list of strings")
        items.append(item)
    return tuple(items)


def _context(name: str, raw: object) -> Context:
    if not isinstance(raw, dict):
        raise TargetError(f"context {name!r} must be a table")
    classification = raw.get("classification")
    if classification not in CLASSIFICATIONS:
        raise TargetError(
            f"context {name!r}: classification must be one of {', '.join(CLASSIFICATIONS)}"
        )
    return Context(
        name,
        str(classification),
        _patterns(raw.get("units"), name, "units", required=True),
        _patterns(raw.get("public"), name, "public", required=False),
    )


def parse_target(text: str) -> Target:
    try:
        raw: object = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TargetError(f"target is not valid TOML: {exc}") from exc
    contexts = raw.get("contexts") if isinstance(raw, dict) else None
    if not isinstance(contexts, dict) or not contexts:
        raise TargetError("target needs a [contexts.<name>] table")
    return Target(tuple(_context(str(n), c) for n, c in sorted(contexts.items())))


def load_target(path: Path) -> Target:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TargetError(f"cannot read {path}: {exc}") from exc
    return parse_target(text)


def target_json(target: Target) -> dict[str, Json]:
    contexts: dict[str, Json] = {}
    for c in target.contexts:
        contexts[c.name] = {
            "classification": c.classification,
            "units": list(c.units),
            "public": list(c.public),
        }
    return {"contexts": contexts}


def _matches(unit_id: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(unit_id, p) for p in patterns)


def assign_units(model: Model, target: Target) -> dict[str, str]:
    assigned: dict[str, str] = {}
    overlaps: dict[str, list[str]] = {}
    for u in model.units:
        owners = sorted(c.name for c in target.contexts if _matches(u.id, c.units))
        if len(owners) > 1:
            overlaps[u.id] = owners
        elif owners:
            assigned[u.id] = owners[0]
    if overlaps:
        raise OverlapError(overlaps)
    return assigned


def is_public(unit_id: str, context: Context) -> bool:
    return _matches(unit_id, context.public)


@dataclass(frozen=True)
class ContextPair:
    source: str
    target: str
    via_public: int
    into_internals: int


@dataclass(frozen=True)
class WorkItem:
    source: str
    target: str
    source_context: str
    target_context: str
    count: int


@dataclass(frozen=True)
class Distance:
    unassigned: list[str]
    pairs: list[ContextPair]
    context_cycles: list[list[str]]
    work_list: list[WorkItem]
    empty_contexts: list[str]


def distance(model: Model, target: Target, na: NotApplicable) -> Distance | None:
    if not require(model, na, "distance", "edges"):
        return None
    assigned = assign_units(model, target)
    by_name = {c.name: c for c in target.contexts}
    public: dict[tuple[str, str], int] = {}
    internal: dict[tuple[str, str], int] = {}
    work: list[WorkItem] = []
    for e in model.edges:
        src, dst = assigned.get(e.source), assigned.get(e.target)
        if src is None or dst is None or src == dst:
            continue
        if is_public(e.target, by_name[dst]):
            public[(src, dst)] = public.get((src, dst), 0) + e.count
        else:
            internal[(src, dst)] = internal.get((src, dst), 0) + e.count
            work.append(WorkItem(e.source, e.target, src, dst, e.count))
    keys = sorted(set(public) | set(internal))
    work.sort(key=lambda w: (w.source_context, w.target_context, -w.count, w.source, w.target))
    return Distance(
        unassigned=sorted(u.id for u in model.units if u.id not in assigned),
        pairs=[ContextPair(s, t, public.get((s, t), 0), internal.get((s, t), 0)) for s, t in keys],
        context_cycles=strongly_connected(sorted(by_name), keys),
        work_list=work,
        empty_contexts=sorted(set(by_name) - set(assigned.values())),
    )


# --- Signals ----------------------------------------------------------------------------------

STOP_TERMS: frozenset[str] = frozenset(
    {
        "manager",
        "service",
        "helper",
        "util",
        "base",
        "mixin",
        "model",
        "view",
        "serializer",
        "schema",
        "dto",
        "data",
        "info",
        "handler",
        "controller",
        "repository",
        "factory",
        "impl",
        "abstract",
        "config",
        "test",
    }
)
MIN_TERM_LENGTH = 3
SCATTER_GROUPS = 3
_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def split_terms(name: str) -> list[str]:
    terms: dict[str, None] = {}
    for part in name.split("_"):
        for word in _WORD.findall(part):
            term = word.lower()
            if len(term) >= MIN_TERM_LENGTH and term not in STOP_TERMS:
                terms.setdefault(term)
    return list(terms)


def unit_terms(unit: Unit) -> frozenset[str]:
    return frozenset(t for decl in unit.types for t in split_terms(decl.name))


@dataclass(frozen=True)
class ScatteredTerm:
    term: str
    groups: list[str]


@dataclass(frozen=True)
class TermSpread:
    distinct: int
    scattered: list[ScatteredTerm]


def term_spread(model: Model, na: NotApplicable) -> TermSpread | None:
    if not require(model, na, "terms", "types"):
        return None
    groups: dict[str, set[str]] = {}
    for u in model.units:
        for term in unit_terms(u):
            groups.setdefault(term, set()).add(u.group)
    scattered = [
        ScatteredTerm(t, sorted(g)) for t, g in sorted(groups.items()) if len(g) >= SCATTER_GROUPS
    ]
    return TermSpread(len(groups), scattered)


@dataclass(frozen=True)
class Richness:
    data_only_share: float | None
    model_types: int
    service_types: int


def model_richness(model: Model, na: NotApplicable) -> Richness | None:
    if not require(model, na, "richness", "types", "data_only", "layer_hints"):
        return None
    model_decls = [d for u in model.units if u.layer_hint in MODEL_LIKE for d in u.types]
    service_types = sum(len(u.types) for u in model.units if u.layer_hint in SERVICE_LIKE)
    share = (
        sum(1 for d in model_decls if d.data_only is True) / len(model_decls)
        if model_decls
        else None
    )
    return Richness(share, len(model_decls), service_types)


@dataclass(frozen=True)
class Entanglement:
    share: float | None
    units: list[str]
    refs: int


def framework_entanglement(
    model: Model, target: Target | None, na: NotApplicable
) -> Entanglement | None:
    if target is None:
        if not require(model, na, "framework", "framework_refs", "layer_hints"):
            return None
        scope = [u for u in model.units if u.layer_hint in MODEL_LIKE]
    else:
        if not require(model, na, "framework", "framework_refs"):
            return None
        assigned = assign_units(model, target)
        generic = {c.name for c in target.contexts if c.classification == "generic"}
        scope = [u for u in model.units if u.id in assigned and assigned[u.id] not in generic]
    entangled = sorted(u.id for u in scope if u.framework_refs)
    refs = sum(len(u.framework_refs) for u in scope)
    return Entanglement(len(entangled) / len(scope) if scope else None, entangled, refs)


@dataclass(frozen=True)
class Escapes:
    total: int
    per_kloc: float | None
    by_kind: dict[str, int]


def escape_totals(model: Model, na: NotApplicable) -> Escapes | None:
    if not require(model, na, "escapes", "escapes"):
        return None
    by_kind: dict[str, int] = {}
    for u in model.units:
        for kind, count in u.escapes.items():
            by_kind[kind] = by_kind.get(kind, 0) + count
    total = sum(by_kind.values())
    loc = sum(u.loc for u in model.units)
    return Escapes(total, total * 1000 / loc if loc else None, dict(sorted(by_kind.items())))


# --- Clustering -------------------------------------------------------------------------------

MAX_SWEEPS = 50
CLUSTER_TERMS = 3
BOTH_ENDS = 2
Weights = dict[str, dict[str, float]]


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    shared = a & b
    return len(shared) / len(a | b) if shared else 0.0


def cluster_weights(model: Model) -> Weights:
    pair: dict[tuple[str, str], float] = {}
    if model.has("edges"):
        for e in model.edges:
            if e.source != e.target:
                key = (e.source, e.target) if e.source < e.target else (e.target, e.source)
                pair[key] = pair.get(key, 0.0) + e.count
    if model.has("types"):
        terms = {u.id: unit_terms(u) for u in model.units}
        ids = [u.id for u in model.units]
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                similarity = _jaccard(terms[a], terms[b])
                if similarity:
                    pair[(a, b)] = pair.get((a, b), 0.0) + 2 * similarity
    weights: Weights = {}
    for (a, b), w in pair.items():
        if w > 0:
            weights.setdefault(a, {})[b] = w
            weights.setdefault(b, {})[a] = w
    return weights


def _best_label(
    neighbours: dict[str, float], labels: dict[str, str], exclude: str | None = None
) -> str | None:
    totals: dict[str, float] = {}
    for other, w in neighbours.items():
        label = labels[other]
        if label != exclude:
            totals[label] = totals.get(label, 0.0) + w
    if not totals:
        return None
    return min(totals, key=lambda label: (-totals[label], label))


def propagate_labels(unit_ids: Sequence[str], weights: Weights) -> dict[str, str]:
    labels = {u: u for u in unit_ids}
    order = sorted(unit_ids)
    for _ in range(MAX_SWEEPS):
        changed = False
        for u in order:
            best = _best_label(weights.get(u, {}), labels)
            if best is not None and best != labels[u]:
                labels[u] = best
                changed = True
        if not changed:
            break
    return labels


def merge_singletons(labels: dict[str, str], weights: Weights) -> dict[str, str]:
    sizes: dict[str, int] = {}
    for label in labels.values():
        sizes[label] = sizes.get(label, 0) + 1
    merged = dict(labels)
    for u in sorted(labels):
        if sizes[labels[u]] != 1:
            continue
        best = _best_label(weights.get(u, {}), labels, exclude=labels[u])
        if best is not None:
            merged[u] = best
    return merged


@dataclass(frozen=True)
class Cluster:
    name: str
    terms: list[str]
    members: list[str]
    cohesion: float | None


@dataclass(frozen=True)
class Clusters:
    clusters: list[Cluster]
    unclustered: list[str]
    separable: bool


def _cohesion(members: set[str], edges: Sequence[Edge]) -> float | None:
    inside = touching = 0
    for e in edges:
        if e.source == e.target:
            continue
        ends = (e.source in members) + (e.target in members)
        if ends:
            touching += e.count
        if ends == BOTH_ENDS:
            inside += e.count
    return inside / touching if touching else None


def cluster_units(model: Model, na: NotApplicable) -> Clusters | None:
    if not model.has("edges") and not model.has("types"):
        na["clusters"] = "missing capability: edges, types"
        return None
    weights = cluster_weights(model)
    ids = [u.id for u in model.units]
    unclustered = [u for u in ids if u not in weights]
    labels = merge_singletons(propagate_labels([u for u in ids if u in weights], weights), weights)
    groups: dict[str, list[str]] = {}
    for u, label in labels.items():
        groups.setdefault(label, []).append(u)
    member_lists = sorted(sorted(members) for members in groups.values())
    by_id = {u.id: u for u in model.units}
    use_types = model.has("types")
    containing: dict[str, int] = {}
    tf_by_cluster: list[dict[str, int]] = []
    for members in member_lists:
        tf: dict[str, int] = {}
        if use_types:
            for u in members:
                for decl in by_id[u].types:
                    for term in split_terms(decl.name):
                        tf[term] = tf.get(term, 0) + 1
        for term in tf:
            containing[term] = containing.get(term, 0) + 1
        tf_by_cluster.append(tf)
    total = len(member_lists)
    clusters: list[Cluster] = []
    for members, tf in zip(member_lists, tf_by_cluster, strict=True):
        scores = {t: n * math.log(total / containing[t]) for t, n in tf.items()}
        top = sorted(scores, key=lambda t: (-scores[t], t))[:CLUSTER_TERMS]
        name = "-".join(top) if top else members[0]
        cohesion = _cohesion(set(members), model.edges) if model.has("edges") else None
        clusters.append(Cluster(name, top, members, cohesion))
    return Clusters(clusters, unclustered, total > 1)


# --- Scorecard --------------------------------------------------------------------------------

BOUNDS: dict[str, tuple[float, float, float, float, float]] = {
    "boundaries": (0, 0.05, 0.15, 0.30, 0.50),
    "language": (0.05, 0.10, 0.20, 0.30, 0.45),
    "model_richness": (0.20, 0.35, 0.50, 0.65, 0.80),
    "framework_isolation": (0, 0.10, 0.25, 0.50, 0.75),
    "type_safety": (0, 1, 3, 6, 10),
}
UNTARGETED_BOUNDARIES_CAP = 4


def score(value: float | None, bounds: tuple[float, float, float, float, float]) -> int | None:
    if value is None:
        return None
    for index, bound in enumerate(bounds):
        if value <= bound:
            return 5 - index
    return 0


@dataclass(frozen=True)
class Scorecard:
    boundaries: int | None
    language: int | None
    model_richness: int | None
    framework_isolation: int | None
    type_safety: int | None


@dataclass(frozen=True)
class Ratchet:
    unit_cycle_members: int | None
    edges_into_internals: int | None
    escapes: int | None
    framework_refs_non_generic: int | None
    unassigned_units: int | None


@dataclass(frozen=True)
class Summary:
    units: int
    loc: int
    groups: int
    edges: int
    skipped: int


@dataclass(frozen=True)
class Assessment:
    language: str
    capabilities: frozenset[str]
    not_applicable: NotApplicable
    summary: Summary
    layout: str | None
    unit_cycles: list[list[str]] | None
    group_cycles: list[list[str]] | None
    hubs: list[Hub] | None
    coupling: list[GroupCoupling] | None
    churn: list[UnitChurn] | None
    terms: TermSpread | None
    richness: Richness | None
    framework: Entanglement | None
    escapes: Escapes | None
    clusters: Clusters | None
    target: Target | None
    distance: Distance | None
    scorecard: Scorecard
    ratchet: Ratchet


def _boundaries_value(
    model: Model, group_cycle_list: list[list[str]] | None, dist: Distance | None
) -> float | None:
    if dist is not None:
        total = sum(e.count for e in model.edges)
        return sum(p.into_internals for p in dist.pairs) / total if total else None
    if group_cycle_list is None or not model.units:
        return None
    cyclic = {g for component in group_cycle_list for g in component}
    return sum(1 for u in model.units if u.group in cyclic) / len(model.units)


def _scorecard(
    model: Model,
    na: NotApplicable,
    group_cycle_list: list[list[str]] | None,
    dist: Distance | None,
    terms: TermSpread | None,
    richness: Richness | None,
    framework: Entanglement | None,
    escapes: Escapes | None,
) -> Scorecard:
    boundaries = score(_boundaries_value(model, group_cycle_list, dist), BOUNDS["boundaries"])
    if boundaries is not None and dist is None:
        boundaries = min(boundaries, UNTARGETED_BOUNDARIES_CAP)
    language = (
        score(len(terms.scattered) / terms.distinct, BOUNDS["language"])
        if terms is not None and terms.distinct
        else None
    )
    card = Scorecard(
        boundaries=boundaries,
        language=language,
        model_richness=score(
            richness.data_only_share if richness else None, BOUNDS["model_richness"]
        ),
        framework_isolation=score(
            framework.share if framework else None, BOUNDS["framework_isolation"]
        ),
        type_safety=score(escapes.per_kloc if escapes else None, BOUNDS["type_safety"]),
    )
    for field in dataclasses.fields(card):
        if getattr(card, field.name) is None:
            na[f"scorecard.{field.name}"] = "no measurable input"
    return card


def _ratchet(
    unit_cycle_list: list[list[str]] | None,
    escapes: Escapes | None,
    framework: Entanglement | None,
    dist: Distance | None,
) -> Ratchet:
    targeted = dist is not None
    return Ratchet(
        unit_cycle_members=(
            sum(len(c) for c in unit_cycle_list) if unit_cycle_list is not None else None
        ),
        edges_into_internals=(
            sum(p.into_internals for p in dist.pairs) if dist is not None else None
        ),
        escapes=escapes.total if escapes is not None else None,
        framework_refs_non_generic=framework.refs if framework is not None and targeted else None,
        unassigned_units=len(dist.unassigned) if dist is not None else None,
    )


def assess(model: Model, target: Target | None, churn_cwd: Path | None) -> Assessment:
    na: NotApplicable = {}
    if target is not None:
        assign_units(model, target)  # rejects overlapping patterns whatever the capabilities
    unit_cycle_list = unit_cycles(model, na)
    group_cycle_list = group_cycles(model, na)
    if churn_cwd is None:
        na["churn"] = "not requested"
        churn_list = None
    else:
        churn_list = churn(model, churn_cwd, na)
    if target is None:
        na["distance"] = "no target"
        dist = None
    else:
        dist = distance(model, target, na)
    terms = term_spread(model, na)
    richness = model_richness(model, na)
    framework = framework_entanglement(model, target, na)
    escapes = escape_totals(model, na)
    summary = Summary(
        units=len(model.units),
        loc=sum(u.loc for u in model.units),
        groups=len({u.group for u in model.units}),
        edges=len(model.edges),
        skipped=len(model.skipped),
    )
    card = _scorecard(model, na, group_cycle_list, dist, terms, richness, framework, escapes)
    return Assessment(
        language=model.language,
        capabilities=model.capabilities,
        not_applicable=na,
        summary=summary,
        layout=layout_style(model, na),
        unit_cycles=unit_cycle_list,
        group_cycles=group_cycle_list,
        hubs=hubs(model, na),
        coupling=coupling(model, na),
        churn=churn_list,
        terms=terms,
        richness=richness,
        framework=framework,
        escapes=escapes,
        clusters=cluster_units(model, na),
        target=target,
        distance=dist,
        scorecard=card,
        ratchet=_ratchet(unit_cycle_list, escapes, framework, dist),
    )


# --- Output -----------------------------------------------------------------------------------

FLOAT_DIGITS = 4


def _to_json(value: object) -> Json:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, frozenset | set):
        return [_to_json(v) for v in sorted(value)]
    if isinstance(value, list | tuple):
        return [_to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise TypeError(f"cannot serialise {type(value).__name__}")


def assessment_json(a: Assessment) -> dict[str, Json]:
    out: dict[str, Json] = {"schema": RESULT_SCHEMA}
    for field in dataclasses.fields(a):
        value = getattr(a, field.name)
        if field.name == "target":
            out["target"] = target_json(value) if isinstance(value, Target) else None
        else:
            out[field.name] = _to_json(value)
    return out


HUMAN_PLACEHOLDER = "<!-- human: see references/report-template.md -->"
CHURN_ROWS = 10
SCATTER_ROWS = 20


def _not_applicable(a: Assessment, key: str) -> str:
    return f"n/a: {a.not_applicable.get(key, 'not computed')}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _score_text(a: Assessment, name: str, value: int | None) -> str:
    return f"{value} / 5" if value is not None else _not_applicable(a, f"scorecard.{name}")


def _summary_lines(a: Assessment) -> list[str]:
    s = a.summary
    return [
        "| Measure | Value |",
        "|---|---|",
        f"| Units | {s.units} |",
        f"| Lines | {s.loc} |",
        f"| Groups | {s.groups} |",
        f"| Edges | {s.edges} |",
        f"| Skipped files | {s.skipped} |",
    ]


def _scorecard_lines(a: Assessment) -> list[str]:
    lines = ["| Dimension | Score |", "|---|---|"]
    for field in dataclasses.fields(a.scorecard):
        lines.append(
            f"| {field.name} | {_score_text(a, field.name, getattr(a.scorecard, field.name))} |"
        )
    lines.append("")
    if a.richness is not None:
        lines.append(
            f"Data-only share in model-like units: {_pct(a.richness.data_only_share)} "
            f"({a.richness.model_types} model types, {a.richness.service_types} service types)."
        )
    else:
        lines.append(f"Model richness: {_not_applicable(a, 'richness')}")
    if a.framework is not None:
        lines.append(
            f"Framework entanglement: {_pct(a.framework.share)} "
            f"({len(a.framework.units)} units, {a.framework.refs} references)."
        )
    else:
        lines.append(f"Framework entanglement: {_not_applicable(a, 'framework')}")
    if a.escapes is not None:
        kinds = ", ".join(f"{k} {n}" for k, n in a.escapes.by_kind.items()) or "none"
        per_kloc = "n/a" if a.escapes.per_kloc is None else f"{a.escapes.per_kloc:.2f}"
        lines.append(f"Type escapes: {a.escapes.total} ({per_kloc} per 1,000 lines): {kinds}.")
    else:
        lines.append(f"Type escapes: {_not_applicable(a, 'escapes')}")
    return lines


def _cycle_lines(title: str, cycles: list[list[str]] | None, reason: str) -> list[str]:
    if cycles is None:
        return [f"{title}: {reason}"]
    if not cycles:
        return [f"{title}: none."]
    return [f"{title}:", *(f"- {', '.join(sorted(c))}" for c in cycles)]


def _hub_lines(a: Assessment) -> list[str]:
    if a.hubs is None:
        lines = [_not_applicable(a, "hubs")]
    elif not a.hubs:
        lines = ["No hubs."]
    else:
        lines = ["| Unit | Importers |", "|---|---|", *(f"| {h.id} | {h.fan_in} |" for h in a.hubs)]
    lines.append("")
    if a.coupling is None:
        lines.append(f"Coupling: {_not_applicable(a, 'coupling')}")
    else:
        lines += ["| Group | Ca | Ce | Instability |", "|---|---|---|---|"]
        for c in a.coupling:
            inst = "n/a" if c.instability is None else f"{c.instability:.2f}"
            lines.append(f"| {c.group} | {c.ca} | {c.ce} | {inst} |")
    return lines


def _churn_lines(a: Assessment) -> list[str]:
    if a.churn is None:
        return [_not_applicable(a, "churn")]
    return [
        "| Unit | Lines changed |",
        "|---|---|",
        *(f"| {c.id} | {c.lines} |" for c in a.churn[:CHURN_ROWS]),
    ]


def _term_lines(a: Assessment) -> list[str]:
    if a.terms is None:
        return [_not_applicable(a, "terms")]
    if not a.terms.scattered:
        return [f"No scattered terms among {a.terms.distinct} distinct terms."]
    rows = [
        f"| {t.term} | {len(t.groups)} | {', '.join(t.groups)} |"
        for t in a.terms.scattered[:SCATTER_ROWS]
    ]
    return [
        f"{len(a.terms.scattered)} of {a.terms.distinct} terms are scattered.",
        "",
        "| Term | Groups | Where |",
        "|---|---|---|",
        *rows,
    ]


def _cluster_lines(a: Assessment) -> list[str]:
    if a.clusters is None:
        return [_not_applicable(a, "clusters")]
    if not a.clusters.separable:
        return ["No separable clusters found."]
    lines: list[str] = []
    for c in a.clusters.clusters:
        cohesion = "n/a" if c.cohesion is None else f"{c.cohesion:.2f}"
        lines.append(
            f"- {c.name} ({len(c.members)} units, cohesion {cohesion}): {', '.join(c.members)}"
        )
    if a.clusters.unclustered:
        lines.append(f"- Unclustered: {', '.join(a.clusters.unclustered)}")
    return lines


def _distance_lines(a: Assessment) -> list[str]:
    d = a.distance
    if d is None:
        return [_not_applicable(a, "distance")]
    lines = [f"Unassigned units: {', '.join(d.unassigned) if d.unassigned else 'none'}.", ""]
    if d.pairs:
        lines += ["| From | To | Via public | Into internals |", "|---|---|---|---|"]
        lines += [
            f"| {p.source} | {p.target} | {p.via_public} | {p.into_internals} |" for p in d.pairs
        ]
    else:
        lines.append("No cross-context edges.")
    lines.append("")
    lines += _cycle_lines("Context cycles", d.context_cycles, "")
    if d.empty_contexts:
        lines += ["", f"Empty contexts (patterns match no unit): {', '.join(d.empty_contexts)}."]
    return lines


def _work_lines(a: Assessment) -> list[str]:
    if a.distance is None:
        return [_not_applicable(a, "distance")]
    if not a.distance.work_list:
        return ["No edges into internals."]
    return [
        "| From | To | Contexts | Count |",
        "|---|---|---|---|",
        *(
            f"| {w.source} | {w.target} | {w.source_context} to {w.target_context} | {w.count} |"
            for w in a.distance.work_list
        ),
    ]


def render_markdown(a: Assessment) -> str:
    missing = sorted(CAPABILITIES - a.capabilities)
    header = [
        "# Migration assessment",
        "",
        f"Language: {a.language}. Capabilities: {', '.join(sorted(a.capabilities)) or 'none'}.",
    ]
    if missing:
        header.append(f"Missing capabilities: {', '.join(missing)}")
    cycles = [
        *_cycle_lines("Unit cycles", a.unit_cycles, _not_applicable(a, "unit_cycles")),
        "",
        *_cycle_lines("Group cycles", a.group_cycles, _not_applicable(a, "group_cycles")),
    ]
    sections: list[tuple[str, list[str]]] = [
        ("Summary", _summary_lines(a)),
        ("Scorecard", _scorecard_lines(a)),
        ("Recommendation", [HUMAN_PLACEHOLDER]),
        ("Layout", [a.layout if a.layout is not None else _not_applicable(a, "layout")]),
        ("Cycles", cycles),
        ("Hubs", _hub_lines(a)),
        ("Churn", _churn_lines(a)),
        ("Scattered terms", _term_lines(a)),
        ("Candidate contexts", _cluster_lines(a)),
        ("Hotspot findings", [HUMAN_PLACEHOLDER]),
        ("Contexts", [HUMAN_PLACEHOLDER]),
        ("Distance to target", _distance_lines(a)),
        ("Work list", _work_lines(a)),
        ("Slices", [HUMAN_PLACEHOLDER]),
    ]
    parts = ["\n".join(header)]
    parts += [f"## {title}\n\n" + "\n".join(lines) for title, lines in sections]
    return "\n\n".join(parts) + "\n"


# --- Command line -----------------------------------------------------------------------------

EXIT_USAGE = 2


def _analyse(args: argparse.Namespace) -> int:
    model = load_model(Path(args.model))
    target = load_target(Path(args.target)) if args.target else None
    result = assess(model, target, Path.cwd() if args.churn else None)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(assessment_json(result), indent=2, sort_keys=True) + "\n"
    (out_dir / "assessment.json").write_text(text, encoding="utf-8")
    (out_dir / "assessment.md").write_text(render_markdown(result), encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="core.py")
    sub = parser.add_subparsers(dest="command", required=True)
    analyse = sub.add_parser("analyse", help="score a neutral model")
    analyse.add_argument("model")
    analyse.add_argument("--out-dir", required=True)
    analyse.add_argument("--target")
    analyse.add_argument("--churn", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    try:
        return _analyse(args)
    except (ModelError, TargetError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
