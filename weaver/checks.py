"""Plan checks beyond overlaps (A4-3, A4-4): findings a build reports on stderr.

A finding names one node and what is wrong with it. A ``strict`` finding fails
``--strict`` (exit 3); the others are notes that never do.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import DIMENSIONS, Plan


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


def findings(plan: Plan) -> tuple[Finding, ...]:
    """Every check's findings, check by check, each in plan order."""
    return unassessed(plan)
