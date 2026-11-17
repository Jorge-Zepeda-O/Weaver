"""Markdown view of a plan (atom A4): the view GitHub renders."""
from __future__ import annotations

from .model import Node, Plan, dimension_key


def to_markdown(plan: Plan) -> str:
    lines = [f"# {plan.title}", ""]
    if plan.goal:
        lines += [f"**Goal:** {plan.goal}", ""]
    if plan.caption:
        lines += [plan.caption, ""]
    lines += [
        "| ID | Kind | Title | Group | Status | Dimensions | Verify | Depends on |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [_row(node) for node in plan.nodes]
    lines += ["", "**Key:**", ""] + [f"- {line}" for line in dimension_key()]

    described = [node for node in plan.nodes if node.notes.strip() or node.decisions]
    if described:
        lines += ["", "## Field notes"]
        for node in described:
            lines += ["", f"### {node.id}: {node.title}"]
            if node.decisions:
                lines += ["", "Decisions: " + ", ".join(node.decisions)]
            if node.notes.strip():
                lines += ["", node.notes.strip()]
    return "\n".join(lines) + "\n"


def verify_text(node: Node) -> str:
    """What proves the node done; a merge with nothing named says so."""
    return node.verify or ("— (unguarded)" if node.unguarded else "—")


def _row(node: Node) -> str:
    deps = ", ".join(d.id if d.seam == "build" else f"{d.id} (runtime)" for d in node.deps)
    cells = [node.id, node.kind, node.title, node.group or "—", node.status_label(),
             node.dimension_label() or "—", verify_text(node), deps or "—"]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _cell(text: str) -> str:
    """Keep a value inside its table cell: no pipe ends it, no newline breaks the row."""
    return " ".join(text.replace("|", "\\|").split())
