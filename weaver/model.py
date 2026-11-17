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

# Every plan-format version this weaver reads (D-4); the newest is the default.
SCHEMA_VERSIONS = (1, 2)
SCHEMA_VERSION = SCHEMA_VERSIONS[-1]
# What a version added: a plan using it must declare at least that version.
KIND_SINCE: dict[str, int] = {"release": 2}

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


def dimension_key() -> tuple[str, ...]:
    """The printed key to ``Node.dimension_label``, one line per dimension."""
    return (*(f"{name[0].upper()} = {name}: " + ", ".join(f"{c} {n}" for c, n in codes.items())
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

    @property
    def unguarded(self) -> bool:
        """A merge or release with nothing named to prove it done."""
        return self.kind in ("merge", "release") and not self.verify

    def dimension_label(self) -> str:
        """``S:L A:- C:M``, or ``""`` when no dimension is assessed."""
        codes = (self.scope, self.amount, self.complexity)
        if not any(codes):
            return ""
        return " ".join(f"{name[0].upper()}:{code or UNASSESSED}"
                        for name, code in zip(DIMENSIONS, codes))


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
