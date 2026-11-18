"""The plan data contract (atom A0).

A plan is a dependency graph of work. Nodes are atoms or merge events; every
edge is a seam, typed by binding time: a build seam (static dependency) or a
runtime seam (dynamic). Edges are stored on the dependent node, so
``Dep(id="A0")`` on node ``A1`` means the edge ``A0 -> A1``.

Every renderer consumes ``Plan`` and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["atom", "merge", "release"]
Status = Literal["todo", "doing", "done", "blocked"]
Seam = Literal["build", "runtime"]

KINDS: tuple[Kind, ...] = ("atom", "merge", "release")
STATUSES: tuple[Status, ...] = ("todo", "doing", "done", "blocked")
SEAMS: tuple[Seam, ...] = ("build", "runtime")
# Status is never shown by fill colour alone (B3). Plain text symbols, not emoji,
# so every view's font has them, the PDF included.
STATUS_SYMBOL: dict[str, str] = {"todo": "○", "doing": "◐", "done": "✓", "blocked": "✕"}

# Every plan-format version this weaver reads (D-4); the newest is the default.
SCHEMA_VERSIONS = (1, 2, 3)
SCHEMA_VERSION = SCHEMA_VERSIONS[-1]
# What a version added: a plan using it must declare at least that version.
KIND_SINCE: dict[str, int] = {"release": 2}
# Node fields, and the plan-level [[overlap]] table, by the schema that introduced them.
FIELD_SINCE: dict[str, int] = {"files": 3, "overlap": 3}

# Node ids end up in Graphviz source, SVG element ids and HTML, so they are
# restricted to characters that are safe verbatim in all three.
NODE_ID_PATTERN = r"[A-Za-z0-9_.-]+"
# "D-3" is a decision of the plan's own project, "other:D-22" one of another.
DECISION_PATTERN = r"(?:[A-Za-z0-9_.-]+:)?D-[0-9]+"

# Task Dimensions: three ordinal scales, low to high, each code with its name.
# "?" means assessed but unknowable and ranks as the worst value; an absent
# value ("") means unassessed. Ordinal: never summed or multiplied.
DIMENSIONS: dict[str, dict[str, str]] = {
    "scope": {"I": "independent", "L": "local", "P": "project", "U": "umbrella",
              "G": "global", "?": "unknowable"},
    "amount": {"1": "one", "F": "few", "N": "numerous", "B": "bulk", "S": "stream",
               "?": "unknowable"},
    "complexity": {"T": "trivial", "E": "easy", "M": "moderate", "H": "hard", "N": "novel",
                   "?": "unknowable"},
}
UNASSESSED = "-"
# Each dimension is a direction of the problem: scope is altitude (reach), amount is
# breadth, complexity is depth. Text arrows, not emoji, so every view's font has them.
DIMENSION_MARKER: dict[str, str] = {"scope": "↕", "amount": "↔", "complexity": "⤓"}


def dimension_key() -> tuple[str, ...]:
    """The printed key to ``Node.dimension_label``, one line per dimension."""
    return (*(f"{DIMENSION_MARKER[name]} {name}: " + ", ".join(f"{c} {n}" for c, n in codes.items())
              for name, codes in DIMENSIONS.items()),
            f"{UNASSESSED} unassessed; ? assessed but unknowable, ranks worst")


@dataclass(frozen=True)
class Dep:
    id: str
    seam: Seam = "build"


@dataclass(frozen=True)
class Node:
    id: str
    title: str
    kind: Kind = "atom"
    status: Status = "todo"
    group: str = ""
    notes: str = ""
    deps: tuple[Dep, ...] = ()
    scope: str = ""
    amount: str = ""
    complexity: str = ""
    verify: str = ""
    decisions: tuple[str, ...] = ()
    files: tuple[str, ...] = ()

    @property
    def unguarded(self) -> bool:
        """A merge or release with nothing named to prove it done."""
        return self.kind in ("merge", "release") and not self.verify

    def status_label(self) -> str:
        """``✓ done``: the symbol and the word."""
        return f"{STATUS_SYMBOL[self.status]} {self.status}"

    def dimension_codes(self) -> tuple[str, ...]:
        """``("↕L", "↔-", "⤓M")`` in DIMENSIONS order, or ``()`` when no dimension is assessed."""
        codes = (self.scope, self.amount, self.complexity)
        if not any(codes):
            return ()
        return tuple(f"{DIMENSION_MARKER[name]}{code or UNASSESSED}"
                     for name, code in zip(DIMENSIONS, codes))

    def dimension_label(self) -> str:
        """``↕L ↔- ⤓M``, or ``""`` when no dimension is assessed."""
        return " ".join(self.dimension_codes())


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    seam: Seam


@dataclass(frozen=True)
class Plan:
    title: str
    nodes: tuple[Node, ...]
    caption: str = ""
    goal: str = ""
    schema: int = SCHEMA_VERSION
    acknowledgements: tuple[Acknowledgement, ...] = ()

    def groups(self) -> tuple[str, ...]:
        """Named groups in order of first appearance; ungrouped nodes belong to none."""
        return tuple(dict.fromkeys(n.group for n in self.nodes if n.group))

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def edges(self) -> tuple[Edge, ...]:
        return tuple(
            Edge(source=dep.id, target=node.id, seam=dep.seam)
            for node in self.nodes
            for dep in node.deps
        )


@dataclass(frozen=True)
class Acknowledgement:
    """A plan-level ``[[overlap]]`` entry (A3-3): ``file`` may be touched by every pair of
    ``nodes``, because of ``reason``. The only source; a node carries no such field."""
    file: str
    nodes: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Overlap:
    """Two nodes on separate tracks that both touch ``file`` (``a`` before ``b`` in plan order).

    ``reason`` comes from the plan's ``[[overlap]]`` entry naming both; ``""`` when none does.
    An acknowledged overlap is still an overlap: it is reported, never hidden (A3-3)."""
    file: str
    a: str
    b: str
    reason: str = ""

    @property
    def acknowledged(self) -> bool:
        return bool(self.reason)

    def describe(self, plan: Plan) -> str:
        """``f.py — A (g) × B (no group)``, then `` — acknowledged: <reason>`` if it is."""
        a, b = plan.node(self.a), plan.node(self.b)
        line = f"{self.file} — {a.id} ({a.group or 'no group'}) × {b.id} ({b.group or 'no group'})"
        return line + (f" — acknowledged: {self.reason}" if self.reason else "")


def overlaps(plan: Plan) -> tuple[Overlap, ...]:
    """Files touched by two nodes that nothing sequences, ordered by file then plan order.

    A node with no group is its own group. Nodes related by a dependency, direct or
    transitive over either seam, are one track; a pair that is entirely ``done`` is history.
    """
    ancestors: dict[str, frozenset[str]] = {}

    def ancestors_of(node_id: str) -> frozenset[str]:
        if node_id not in ancestors:
            direct = [d.id for d in plan.node(node_id).deps]
            ancestors[node_id] = frozenset(direct).union(*(ancestors_of(d) for d in direct))
        return ancestors[node_id]

    touching: dict[str, list[Node]] = {}
    for node in plan.nodes:
        for file in node.files:
            touching.setdefault(file, []).append(node)

    found = []
    for file in sorted(touching):
        nodes = touching[file]
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if (a.group, a.id if not a.group else "") == (b.group, b.id if not b.group else ""):
                    continue
                if a.status == b.status == "done":
                    continue
                if a.id in ancestors_of(b.id) or b.id in ancestors_of(a.id):
                    continue
                reason = next((ack.reason for ack in plan.acknowledgements
                               if ack.file == file and {a.id, b.id} <= set(ack.nodes)), "")
                found.append(Overlap(file, a.id, b.id, reason))
    return tuple(found)
