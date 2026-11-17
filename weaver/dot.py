"""Graphviz export: DOT source and inline-ready SVG (atom A2).

Every node statement carries ``id="node-<id>"``, so the SVG group for node X
is ``<g id="node-X" class="node">``. That id is the contract with the HTML view
(A3) and the PDF view (A5).
"""
from __future__ import annotations

import re
import subprocess

from .model import Node, Plan

DOT = "/usr/bin/dot"

_FILL = {"todo": "#ffffff", "doing": "#dbeafe", "done": "#dcfce7", "blocked": "#fee2e2"}
_SHAPE = {"atom": 'shape=box, style="rounded,filled"', "merge": "shape=hexagon, style=filled"}
_PROLOG = re.compile(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>")
# Graphviz 2.43 writes '-' in attribute values as '&#45;'; ids are restored to
# their literal form so the contract holds for text matching as well as for parsers.
_ID_ATTR = re.compile(r' id="([^"]*)"')


def _quote(text: str) -> str:
    """A DOT double-quoted string: backslash and quote escaped, newlines as \\n."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped.replace("\r\n", "\n").replace("\n", "\\n") + '"'


def _node_statement(node: Node) -> str:
    label = _quote(node.id + "\n" + node.title)
    return (f'  "{node.id}" [id="node-{node.id}", label={label}, '
            f'{_SHAPE[node.kind]}, fillcolor="{_FILL[node.status]}"];')


def to_dot(plan: Plan) -> str:
    lines = [
        "digraph plan {",
        "  rankdir=LR;",
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica"];',
    ]
    lines += [_node_statement(node) for node in plan.nodes]
    for edge in plan.edges():
        style = " [style=dashed]" if edge.seam == "runtime" else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}"{style};')
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(plan: Plan) -> str:
    """Run Graphviz; return SVG without XML prolog or DOCTYPE, ready to inline."""
    result = subprocess.run([DOT, "-Tsvg"], input=to_dot(plan), capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"dot exited with {result.returncode}: {result.stderr.strip()}")
    svg = _PROLOG.sub("", result.stdout)
    svg = _ID_ATTR.sub(lambda m: ' id="' + m.group(1).replace("&#45;", "-") + '"', svg)
    return svg.strip() + "\n"
