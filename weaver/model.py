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
FIELD_SINCE: dict[str, int] = {"files": 3, "overlap": 3, "reworks": 3}

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
    # A3-11: earlier nodes this one fixes. Nodes are only added; a fix never reopens one.
    reworks: tuple[str, ...] = ()

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
    An acknowledged overlap is still an overlap: it is reported, never hidden (A3-3).
    ``landed`` is the side that already landed in the merge or release ``landed_in``
    (A4-1); both ``""`` when neither side has."""
    file: str
    a: str
    b: str
    reason: str = ""
    landed: str = ""
    landed_in: str = ""

    @property
    def acknowledged(self) -> bool:
        return bool(self.reason)

    def describe(self, plan: Plan) -> str:
        """``f.py — A (g) × B (no group)``, then the landing hint, then
        `` — acknowledged: <reason>`` if it is."""
        a, b = plan.node(self.a), plan.node(self.b)
        line = f"{self.file} — {a.id} ({a.group or 'no group'}) × {b.id} ({b.group or 'no group'})"
        if self.landed:
            other = self.b if self.landed == self.a else self.a
            where = "" if self.landed_in == self.landed else f" in {self.landed_in}"
            line += (f" — {self.landed} landed{where}: if {other} builds on {self.landed_in}, "
                     f"add it to {other}'s deps")
        return line + (f" — acknowledged: {self.reason}" if self.reason else "")


def _closure(plan: Plan, node_id: str, seams: tuple[Seam, ...],
             memo: dict[str, frozenset[str]]) -> frozenset[str]:
    """Every node ``node_id`` depends on, transitively, over the given seams."""
    if node_id not in memo:
        direct = [d.id for d in plan.node(node_id).deps if d.seam in seams]
        memo[node_id] = frozenset(direct).union(*(_closure(plan, d, seams, memo) for d in direct))
    return memo[node_id]


def landings(plan: Plan) -> dict[str, str]:
    """A4-1: each landed node → the merge or release it first landed in.

    A node has landed when it is done and a done merge or release depends on it over build
    seams (a runtime seam consumes output, it merges no code), or when it is that done merge
    or release itself. Under D-21 only a landed node is on ``main``; done alone is not merged.
    The first landing is one no other candidate lies upstream of; ties go to plan order.
    """
    memo: dict[str, frozenset[str]] = {}
    gates = [n for n in plan.nodes if n.kind in ("merge", "release") and n.status == "done"]
    found: dict[str, str] = {}
    for node in plan.nodes:
        if node.status != "done":
            continue
        if node in gates:
            found[node.id] = node.id
            continue
        candidates = [g.id for g in gates if node.id in _closure(plan, g.id, ("build",), memo)]
        first = [c for c in candidates
                 if not any(o in _closure(plan, c, ("build",), memo) for o in candidates)]
        if first:
            found[node.id] = first[0]
    return found


def overlaps(plan: Plan) -> tuple[Overlap, ...]:
    """Files touched by two nodes that nothing sequences, ordered by file then plan order.

    A node with no group is its own group. Nodes related by a dependency, direct or
    transitive over either seam, are one track. A pair where both sides landed is history
    (A4-1; v0.3 took any done pair as history, but done is not merged under D-21).
    """
    ancestors: dict[str, frozenset[str]] = {}

    def ancestors_of(node_id: str) -> frozenset[str]:
        return _closure(plan, node_id, SEAMS, ancestors)

    landed = landings(plan)

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
                if a.id in landed and b.id in landed:
                    continue
                if a.id in ancestors_of(b.id) or b.id in ancestors_of(a.id):
                    continue
                reason = next((ack.reason for ack in plan.acknowledgements
                               if ack.file == file and {a.id, b.id} <= set(ack.nodes)), "")
                side = a.id if a.id in landed else b.id if b.id in landed else ""
                found.append(Overlap(file, a.id, b.id, reason, side, landed.get(side, "")))
    return tuple(found)


def _track(node: Node) -> tuple[str, str]:
    """A node with no group is its own group."""
    return (node.group, "" if node.group else node.id)


@dataclass(frozen=True)
class StaleAcknowledgement:
    """A4-2: node ``node`` of the ``entry``-th ``[[overlap]]`` (0-based) on ``file`` no longer
    overlaps any other node the entry names, because the structure changed."""
    file: str
    node: str
    why: str
    entry: int

    def describe(self) -> str:
        return f"{self.file} — {self.node} {self.why}"


def acknowledgement_report(plan: Plan) -> tuple[tuple[StaleAcknowledgement, ...], int]:
    """A4-2: the stale nodes of every ``[[overlap]]`` entry, and how many entries are history.

    For each pair an entry names: one lane or a dependency path → sequenced; both landed →
    history (A4-1); otherwise the overlap is open. A node with no open or history pair left
    is stale: the entry claims an overlap the plan no longer has. An entry with no open pair
    but at least one history pair is history: true, but prunable.
    """
    memo: dict[str, frozenset[str]] = {}
    landed = landings(plan)

    def kind(x: Node, y: Node) -> str:
        if _track(x) == _track(y) or x.id in _closure(plan, y.id, SEAMS, memo) \
                or y.id in _closure(plan, x.id, SEAMS, memo):
            return "sequenced"
        return "history" if x.id in landed and y.id in landed else "open"

    stale: list[StaleAcknowledgement] = []
    history = 0
    for index, ack in enumerate(plan.acknowledgements):
        named = [plan.node(i) for i in ack.nodes]
        kinds = {(x.id, y.id): kind(x, y) for x in named for y in named if x.id != y.id}
        for x in named:
            if all(k == "sequenced" for (a, _), k in kinds.items() if a == x.id):
                stale.append(StaleAcknowledgement(
                    ack.file, x.id, "shares a lane or a dependency with every other node named",
                    index))
        values = set(kinds.values())
        if "open" not in values and "history" in values:
            history += 1
    return tuple(stale), history
