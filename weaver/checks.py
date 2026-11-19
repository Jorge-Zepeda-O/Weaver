"""Plan checks beyond overlaps (A4-3, A4-4): findings a build reports on stderr.

A finding names one node and what is wrong with it. A ``strict`` finding fails
``--strict`` (exit 3); the others are notes that never do.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import DIMENSIONS, SEAMS, Plan, _closure


# How the build summary counts each check: (one, many).
SUMMARY: dict[str, tuple[str, str]] = {
    "unassessed": ("unassessed", "unassessed"),
    "orphan release": ("orphan release", "orphan releases"),
    "unordered releases": ("unordered release pair", "unordered release pairs"),
    "done on unfinished": ("done node on unfinished work", "done nodes on unfinished work"),
}


def summary(found: tuple[Finding, ...]) -> str:
    """``, 2 unassessed, 1 orphan release`` in check order; ``""`` when nothing was found."""
    counts = {check: sum(f.check == check for f in found) for check in SUMMARY}
    return "".join(f", {n} {SUMMARY[check][n != 1]}" for check, n in counts.items() if n)


@dataclass(frozen=True)
class Finding:
    check: str
    node: str
    detail: str
    strict: bool = True

    def describe(self) -> str:
        return f"{self.check}: {self.node} — {self.detail}"


def unassessed(plan: Plan) -> tuple[Finding, ...]:
    """A4-3: every node carries all three dimensions, whatever its status. '?' is an
    assessment (unknowable); only an absent value is unassessed."""
    found = []
    for node in plan.nodes:
        missing = [name for name in DIMENSIONS if not getattr(node, name)]
        if missing:
            found.append(Finding("unassessed", node.id, "no " + ", ".join(missing)))
    return tuple(found)


def release_order(plan: Plan) -> tuple[Finding, ...]:
    """A4-4: every release but the first depends on some release, directly or not (an orphan
    fails --strict). Two releases neither depending on the other get a note that never
    fails --strict: a hotfix beside a newer release is legitimate, a release that skipped
    the one before it is not, and only a person can tell them apart. Of the releases with
    no release upstream, the first in the file is the first (A5-1's tie-break)."""
    memo: dict[str, frozenset[str]] = {}
    releases = [n.id for n in plan.nodes if n.kind == "release"]
    upstream = {r: _closure(plan, r, SEAMS, memo) for r in releases}
    roots = [r for r in releases if not any(o in upstream[r] for o in releases)]
    orphans = roots[1:]
    found = [Finding("orphan release", r, f"depends on no release; the first release is {roots[0]}")
             for r in orphans]
    ordered = [r for r in releases if r not in orphans]
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if a not in upstream[b] and b not in upstream[a]:
                found.append(Finding("unordered releases", b,
                                     f"neither {a} nor {b} depends on the other", strict=False))
    return tuple(found)


def done_on_unfinished(plan: Plan) -> tuple[Finding, ...]:
    """A4-4: a done node may not depend, over a build seam, on a node that is not done; it is
    the slip nobody recorded (a done release still listing work that moved on). Over a
    runtime seam it may be legitimate (consumed late), so it is a note for a person to weigh
    while planning, never failing --strict."""
    status = {node.id: node.status for node in plan.nodes}
    return tuple(Finding("done on unfinished", node.id,
                         f"depends{' at runtime' * (dep.seam == 'runtime')} on {dep.id}, "
                         f"which is {status[dep.id]}", strict=dep.seam == "build")
                 for node in plan.nodes if node.status == "done"
                 for dep in node.deps if status[dep.id] != "done")


def findings(plan: Plan) -> tuple[Finding, ...]:
    """Every check's findings, check by check, each in plan order."""
    return unassessed(plan) + release_order(plan) + done_on_unfinished(plan)
