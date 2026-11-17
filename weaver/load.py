"""Load and validate a plan file (atom A1).

``load_plan`` either returns a fully valid ``Plan`` or raises ``PlanError``
listing *every* problem found, so one run shows all the fixes owed.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from .model import KINDS, NODE_ID_PATTERN, SEAMS, STATUSES, Dep, Node, Plan

_NODE_ID = re.compile(rf"^{NODE_ID_PATTERN}$")
_PLAN_KEYS = {"title", "caption"}
_NODE_KEYS = {"id", "title", "kind", "status", "owner", "notes", "deps", "runtime_deps"}
_DEP_KEYS: dict[str, str] = {"deps": "build", "runtime_deps": "runtime"}


class PlanError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("invalid plan:\n" + "\n".join(f"  - {e}" for e in errors))


def load_plan(path: str | Path) -> Plan:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PlanError([f"not valid TOML: {exc}"]) from exc
    return parse_plan(data)


def parse_plan(data: dict[str, Any]) -> Plan:
    errors: list[str] = []
    header = data.get("plan")
    raw_nodes = data.get("node")

    title = ""
    caption = ""
    if not isinstance(header, dict):
        errors.append("missing [plan] table")
    else:
        errors += [f"[plan]: unknown key '{k}'" for k in sorted(set(header) - _PLAN_KEYS)]
        title = _string(header, "title", "[plan]", errors, required=True)
        caption = _string(header, "caption", "[plan]", errors)
    errors += [f"unknown top-level key '{k}'" for k in sorted(set(data) - {"plan", "node"})]

    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append("no [[node]] entries")
        raw_nodes = []

    nodes = [n for n in (_parse_node(i, raw, errors) for i, raw in enumerate(raw_nodes)) if n]
    _check_ids_and_refs(nodes, errors)
    if not errors:
        _check_acyclic(nodes, errors)

    if errors:
        raise PlanError(errors)
    return Plan(title=title, caption=caption, nodes=tuple(nodes))


def _parse_node(index: int, raw: Any, errors: list[str]) -> Node | None:
    where = f"node #{index + 1}"
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a table")
        return None
    node_id = raw.get("id")
    if isinstance(node_id, str) and node_id:
        where = f"node '{node_id}'"
    errors_before = len(errors)

    errors += [f"{where}: unknown key '{k}'" for k in sorted(set(raw) - _NODE_KEYS)]
    if not isinstance(node_id, str) or not _NODE_ID.match(node_id):
        errors.append(f"{where}: 'id' must match {NODE_ID_PATTERN}")
    title = _string(raw, "title", where, errors, required=True)
    kind = _choice(raw, "kind", KINDS, where, errors)
    status = _choice(raw, "status", STATUSES, where, errors)
    owner = _string(raw, "owner", where, errors)
    notes = _string(raw, "notes", where, errors)

    deps: list[Dep] = []
    for key, seam in _DEP_KEYS.items():
        value = raw.get(key, [])
        if not isinstance(value, list) or not all(isinstance(d, str) for d in value):
            errors.append(f"{where}: '{key}' must be a list of node ids")
            continue
        deps += [Dep(id=d, seam=seam) for d in value]  # type: ignore[arg-type]

    if len(errors) > errors_before:
        return None
    return Node(id=node_id, title=title, kind=kind, status=status,  # type: ignore[arg-type]
                owner=owner, notes=notes, deps=tuple(deps))


def _string(table: dict[str, Any], key: str, where: str, errors: list[str],
            required: bool = False) -> str:
    value = table.get(key)
    if value is None:
        if required:
            errors.append(f"{where}: missing '{key}'")
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        errors.append(f"{where}: '{key}' must be a non-empty string" if required
                      else f"{where}: '{key}' must be a string")
        return ""
    return value


def _choice(table: dict[str, Any], key: str, allowed: tuple[str, ...], where: str,
            errors: list[str]) -> str:
    value = table.get(key, allowed[0])
    if value not in allowed:
        errors.append(f"{where}: '{key}' must be one of {', '.join(allowed)} (got {value!r})")
        return allowed[0]
    return value


def _check_ids_and_refs(nodes: list[Node], errors: list[str]) -> None:
    seen: set[str] = set()
    for node in nodes:
        if node.id in seen:
            errors.append(f"duplicate node id '{node.id}'")
        seen.add(node.id)
    for node in nodes:
        dep_ids = [d.id for d in node.deps]
        for dep_id in dep_ids:
            if dep_id == node.id:
                errors.append(f"node '{node.id}': depends on itself")
            elif dep_id not in seen:
                errors.append(f"node '{node.id}': unknown dependency '{dep_id}'")
        for dep_id in sorted({d for d in dep_ids if dep_ids.count(d) > 1}):
            errors.append(f"node '{node.id}': '{dep_id}' listed more than once "
                          "(a dependency has exactly one seam type)")


def _check_acyclic(nodes: list[Node], errors: list[str]) -> None:
    deps_of = {n.id: [d.id for d in n.deps] for n in nodes}
    done: set[str] = set()

    def visit(node_id: str, path: list[str]) -> list[str] | None:
        if node_id in path:
            return path[path.index(node_id):] + [node_id]
        if node_id in done:
            return None
        for dep_id in deps_of[node_id]:
            cycle = visit(dep_id, path + [node_id])
            if cycle:
                return cycle
        done.add(node_id)
        return None

    for node in nodes:
        cycle = visit(node.id, [])
        if cycle:
            # Report in dependency direction: first -> ... -> back to first.
            errors.append("dependency cycle: " + " -> ".join(reversed(cycle)))
            return
