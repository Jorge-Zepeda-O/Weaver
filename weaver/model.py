"""The plan data contract (atom A0).

A plan is a dependency graph of work. Nodes are atoms or merge events; every
edge is a seam, typed by binding time: a build seam (static dependency) or a
runtime seam (dynamic). Edges are stored on the dependent node, so ``Dep(id="A0")`` on node ``A1``
means the edge ``A0 -> A1``.

Every renderer consumes ``Plan`` and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["atom", "merge"]
Status = Literal["todo", "doing", "done", "blocked"]
Seam = Literal["build", "runtime"]

KINDS: tuple[Kind, ...] = ("atom", "merge")
STATUSES: tuple[Status, ...] = ("todo", "doing", "done", "blocked")
SEAMS: tuple[Seam, ...] = ("build", "runtime")

# Node ids end up in Graphviz source, SVG element ids and HTML, so they are
# restricted to characters that are safe verbatim in all three.
NODE_ID_PATTERN = r"[A-Za-z0-9_.-]+"


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
    owner: str = ""
    notes: str = ""
    deps: tuple[Dep, ...] = ()


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
