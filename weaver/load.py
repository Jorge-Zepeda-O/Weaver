"""Load and validate a plan file (atom A1).

``load_plan`` either returns a fully valid ``Plan`` or raises ``PlanError``
listing *every* problem found, so one run shows all the fixes owed.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from .model import (DECISION_PATTERN, DIMENSIONS, FIELD_SINCE, KIND_SINCE, KINDS,
                    NODE_ID_PATTERN, SCHEMA_VERSION, SCHEMA_VERSIONS, STATUSES, Dep, Node, Plan)

_NODE_ID = re.compile(rf"^{NODE_ID_PATTERN}$")
_DECISION = re.compile(rf"^{DECISION_PATTERN}$")
_PLAN_KEYS = {"schema", "title", "goal", "caption"}
_NODE_KEYS = {"id", "title", "kind", "status", "group", "notes", "deps", "runtime_deps",
              "verify", "decisions", "files", *DIMENSIONS}
# Keys an older plan may still carry, with what replaced them.
_RENAMED = {"owner": "group"}
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

    title = goal = caption = ""
    schema = SCHEMA_VERSION
    if not isinstance(header, dict):
        errors.append("missing [plan] table")
    else:
        schema = _check_schema(header, errors)
        errors += [f"[plan]: unknown key '{k}'" for k in sorted(set(header) - _PLAN_KEYS)]
        title = _string(header, "title", "[plan]", errors, required=True)
        goal = _string(header, "goal", "[plan]", errors)
        caption = _string(header, "caption", "[plan]", errors)
    errors += [f"unknown top-level key '{k}'" for k in sorted(set(data) - {"plan", "node"})]

    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append("no [[node]] entries")
        raw_nodes = []

    nodes = [n for n in (_parse_node(i, raw, schema, errors) for i, raw in enumerate(raw_nodes))
             if n]
    _check_ids_and_refs(nodes, errors)
    if not errors:
        _check_acyclic(nodes, errors)

    if errors:
        raise PlanError(errors)
    return Plan(title=title, goal=goal, caption=caption, nodes=tuple(nodes), schema=schema)


def _parse_node(index: int, raw: Any, schema: int, errors: list[str]) -> Node | None:
    where = f"node #{index + 1}"
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a table")
        return None
    node_id = raw.get("id")
    if isinstance(node_id, str) and node_id:
        where = f"node '{node_id}'"
    errors_before = len(errors)

    errors += [f"{where}: unknown key '{k}'" + (f" (renamed to '{_RENAMED[k]}' in schema 1)"
                                                if k in _RENAMED else "")
               for k in sorted(set(raw) - _NODE_KEYS)]
    if not isinstance(node_id, str) or not _NODE_ID.match(node_id):
        errors.append(f"{where}: 'id' must match {NODE_ID_PATTERN}")
    title = _string(raw, "title", where, errors, required=True)
    kind = _choice(raw, "kind", KINDS, where, errors)
    if KIND_SINCE.get(kind, 1) > schema:
        errors.append(f"{where}: kind '{kind}' needs schema = {KIND_SINCE[kind]}")
    status = _choice(raw, "status", STATUSES, where, errors)
    group = _string(raw, "group", where, errors)
    notes = _string(raw, "notes", where, errors)
    verify = _string(raw, "verify", where, errors)
    dimensions = {name: _code(raw, name, tuple(codes), where, errors)
                  for name, codes in DIMENSIONS.items()}
    decisions = _decisions(raw, where, errors)
    if "files" in raw and FIELD_SINCE["files"] > schema:
        errors.append(f"{where}: field 'files' needs schema = {FIELD_SINCE['files']}")
    files = _files(raw, where, errors)

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
                group=group, notes=notes, deps=tuple(deps), verify=verify,
                decisions=decisions, files=files, **dimensions)


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


def _check_schema(header: dict[str, Any], errors: list[str]) -> int:
    """The plan's format version; a missing or unknown one is refused, never guessed at.

    On error the newest version is returned, so node checks run once and report
    only their own faults.
    """
    version = header.get("schema")
    readable = " or ".join([", ".join(map(str, SCHEMA_VERSIONS[:-1])), str(SCHEMA_VERSIONS[-1])])
    if version is None:
        errors.append(f"[plan]: missing 'schema' (this version of weaver reads schema = {readable})")
    elif not isinstance(version, int) or isinstance(version, bool):
        errors.append("[plan]: 'schema' must be an integer")
    elif version not in SCHEMA_VERSIONS:
        errors.append(f"[plan]: unsupported schema {version} "
                      f"(this version of weaver reads schema = {readable})")
    else:
        return version
    return SCHEMA_VERSION


def _code(table: dict[str, Any], key: str, allowed: tuple[str, ...], where: str,
          errors: list[str]) -> str:
    """An optional controlled-vocabulary code; absent means unassessed (``""``)."""
    value = table.get(key)
    if value is None:
        return ""
    if value not in allowed:
        errors.append(f"{where}: '{key}' must be one of {', '.join(allowed)} (got {value!r})")
        return ""
    return value


def _decisions(raw: dict[str, Any], where: str, errors: list[str]) -> tuple[str, ...]:
    value = raw.get("decisions", [])
    if not isinstance(value, list) or not all(isinstance(d, str) for d in value):
        errors.append(f"{where}: 'decisions' must be a list of decision handles")
        return ()
    bad = [d for d in value if not _DECISION.match(d)]
    errors += [f"{where}: '{d}' is not a decision handle (D-3, or project:D-3)" for d in bad]
    return () if bad else tuple(value)


def _files(raw: dict[str, Any], where: str, errors: list[str]) -> tuple[str, ...]:
    """Paths a node touches, normalised (no leading ``./`` or trailing ``/``) and deduplicated."""
    value = raw.get("files", [])
    paths = ([f.removeprefix("./").removesuffix("/") for f in value]
             if isinstance(value, list) and all(isinstance(f, str) for f in value) else None)
    # Checked after normalising, so "./" or "/" cannot slip through as an empty path.
    if paths is None or not all(p.strip() for p in paths):
        errors.append(f"{where}: 'files' must be a list of non-empty strings")
        return ()
    return tuple(dict.fromkeys(paths))


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
