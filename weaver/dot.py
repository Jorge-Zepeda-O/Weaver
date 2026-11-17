"""Graphviz export: DOT source and inline-ready SVG (atom A2).

Every node statement carries ``id="node-<id>"``, so the SVG group for node X
is ``<g id="node-X" class="node">``. That id is the contract with the HTML view
(A3) and the PDF view (A5).

Encoding: shape = kind, fill = status, edge style = seam, lane = group, border
colour = scope, border weight = complexity, dashed border = unguarded merge.
The dimension codes are printed in the label too, so colour never carries
meaning alone.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap

from .model import Node, Plan

# Titles wrap at word boundaries, so a long title grows a node down, not across.
TITLE_WIDTH = 28

_FILL = {"todo": "#ffffff", "doing": "#dbeafe", "done": "#dcfce7", "blocked": "#fee2e2"}
_SHAPE = {"atom": ("box", "rounded,filled"), "merge": ("hexagon", "filled"),
          "release": ("octagon", "filled")}
# A release's text is purple; its border stays scope's (D-15). Shape marks it too.
RELEASE_COLOUR = "#7e22ce"
# Heat scale, cool to hot; "?" ranks worst, so it sits past global.
SCOPE_COLOUR = {"I": "#2563eb", "L": "#0891b2", "P": "#ca8a04", "U": "#ea580c",
                "G": "#dc2626", "?": "#7f1d1d"}
COMPLEXITY_WIDTH = {"T": "1", "E": "1.5", "M": "2.5", "H": "3.5", "N": "5", "?": "5"}
LANE_COLOUR = "#94a3b8"
_PROLOG = re.compile(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>")
# Graphviz 2.43 writes '-' in attribute values as '&#45;'; ids and classes are restored
# to their literal form so the contract holds for text matching as well as for parsers.
_ID_OR_CLASS_ATTR = re.compile(r' (id|class)="([^"]*)"')


def node_classes(node: Node) -> str:
    """Classes for the page's stylesheet (D-13); ``?`` becomes ``unknown`` to stay a plain CSS name."""
    classes = [f"kind-{node.kind}", f"status-{node.status}"]
    for name in ("scope", "amount", "complexity"):
        code = getattr(node, name)
        if code:
            classes.append(f"{name}-{'unknown' if code == '?' else code}")
    if node.unguarded:
        classes.append("unguarded")
    return " ".join(classes)


def _quote(text: str) -> str:
    """A DOT double-quoted string: backslash and quote escaped, newlines as \\n."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped.replace("\r\n", "\n").replace("\n", "\\n") + '"'


def _node_statement(node: Node, indent: str = "  ") -> str:
    title = textwrap.wrap(node.title, TITLE_WIDTH, break_long_words=False, break_on_hyphens=False)
    label = _quote("\n".join(filter(None, [node.id, *title, node.dimension_label()])))
    shape, style = _SHAPE[node.kind]
    if node.unguarded:
        style += ",dashed"
    style_attr = f'"{style}"' if "," in style else style
    attrs = [f'id="node-{node.id}"', f'class="{node_classes(node)}"', f"label={label}",
             f"shape={shape}", f"style={style_attr}",
             f'fillcolor="{_FILL[node.status]}"']
    if node.kind == "release":
        attrs.append(f'fontcolor="{RELEASE_COLOUR}"')
    if node.scope:
        attrs.append(f'color="{SCOPE_COLOUR[node.scope]}"')
    if node.complexity:
        attrs.append(f"penwidth={COMPLEXITY_WIDTH[node.complexity]}")
    return f'{indent}"{node.id}" [{", ".join(attrs)}];'


def to_dot(plan: Plan) -> str:
    lines = [
        "digraph plan {",
        "  rankdir=LR;",
        "  newrank=true;  // rank globally, so a lane spanning the history cannot pull its ends together",
        '  graph [fontname="Helvetica", fontsize=11];',
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica"];',
    ]
    for index, group in enumerate(plan.groups()):
        lines += [f'  subgraph "cluster_{index}" {{',
                  f"    label={_quote(group)};",
                  '    class="lane";',
                  f'    style="rounded,dashed"; color="{LANE_COLOUR}"; fontcolor="#475569";']
        lines += [_node_statement(n, "    ") for n in plan.nodes if n.group == group]
        lines.append("  }")
    lines += [_node_statement(n) for n in plan.nodes if not n.group]
    for edge in plan.edges():
        style = ", style=dashed" if edge.seam == "runtime" else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}" [class="seam-{edge.seam}"{style}];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(plan: Plan) -> str:
    """Run Graphviz; return SVG without XML prolog or DOCTYPE, ready to inline."""
    dot = shutil.which("dot")
    if dot is None:
        raise RuntimeError("Graphviz is not installed: no 'dot' on the PATH (https://graphviz.org/download/)")
    result = subprocess.run([dot, "-Tsvg"], input=to_dot(plan), capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"dot exited with {result.returncode}: {result.stderr.strip()}")
    svg = _PROLOG.sub("", result.stdout)
    svg = _ID_OR_CLASS_ATTR.sub(lambda m: f' {m.group(1)}="' + m.group(2).replace("&#45;", "-") + '"',
                                svg)
    return svg.strip() + "\n"
