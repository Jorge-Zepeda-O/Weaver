"""Markdown view of a plan (atom A4): the view GitHub renders."""
from __future__ import annotations

from .model import Node, Plan


def to_markdown(plan: Plan) -> str:
    lines = [f"# {plan.title}", ""]
    if plan.caption:
        lines += [plan.caption, ""]
    lines += [
        "| ID | Kind | Title | Status | Owner | Depends on |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_row(node) for node in plan.nodes]

    noted = [node for node in plan.nodes if node.notes.strip()]
    if noted:
        lines += ["", "## Field notes"]
        for node in noted:
            lines += ["", f"### {node.id}: {node.title}", "", node.notes.strip()]
    return "\n".join(lines) + "\n"


def _row(node: Node) -> str:
    deps = ", ".join(d.id if d.seam == "build" else f"{d.id} (runtime)" for d in node.deps)
    cells = [node.id, node.kind, node.title, node.status, node.owner, deps or "—"]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _cell(text: str) -> str:
    """Keep a value inside its table cell: no pipe ends it, no newline breaks the row."""
    return " ".join(text.replace("|", "\\|").split())
