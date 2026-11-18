"""Graphviz export: DOT source and inline-ready SVG (atom A2).

Every node statement carries ``id="node-<id>"``, so the SVG group for node X
is ``<g id="node-X" class="node">``. That id is the contract with the HTML view
(A3) and the PDF view (A5).

Encoding: shape = kind, fill = status, edge style = seam, lane = group, colour of
the scope code = scope, border colour and weight = complexity, outline count = amount,
dashed border = unguarded merge. Status and the dimension codes are printed in
the label too, so colour never carries meaning alone.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap

from .model import STATUSES, Node, Plan
from .tokens import LIGHT

# Titles wrap at word boundaries, so a long title grows a node down, not across.
TITLE_WIDTH = 28

# Colours come from the tokens (B0), so the standalone SVG and the PDF match the page.
_FILL = {status: LIGHT[f"status-{status}"] for status in STATUSES}
_SHAPE = {"atom": ("box", "rounded,filled"), "merge": ("hexagon", "filled"),
          "release": ("octagon", "filled")}
# A release's text is bold purple, a colour no scope uses (D-15); its scope stays in the code.
RELEASE_COLOUR = LIGHT["release"]


def _token_map(prefix: str, codes: str) -> dict[str, str]:
    return {c: LIGHT[f"{prefix}-{'unknown' if c == '?' else c}"] for c in codes}


# D-18: the border is the node's weight (complexity: colour and width, so it never rests on
# colour vision alone); the text is its reach (scope). "?" ranks worst in both.
SCOPE_TEXT_COLOUR = _token_map("scope-text", "ILPUG?")
COMPLEXITY_COLOUR = _token_map("complexity", "TEMHN?")
COMPLEXITY_WIDTH = {"T": "1", "E": "1.5", "M": "2.5", "H": "3.5", "N": "5", "?": "5"}
# D-16: amount is the number of outlines, uncapped on purpose: a huge node should look
# like a wall and ask to be broken down. "?" ranks worst, as many as stream.
AMOUNT_OUTLINES = {"1": "1", "F": "2", "N": "3", "B": "4", "S": "5", "?": "5"}
LANE_COLOUR = LIGHT["lane"]
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


def _html(text: str) -> str:
    """Text for an HTML-like label: every markup character becomes an entity, so a title
    is drawn as written and can never open a tag or end the label. Graphviz still expands
    escapes like \\N (node name) inside HTML labels, even from an entity, so a backslash
    is doubled."""
    return (text.replace("\\", "\\\\").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _card(node: Node) -> str:
    """B4: the node's label as a table: bold id and status, the wrapped title, the codes.
    Only the scope code is coloured (D-18); a release's text is all purple (D-15)."""
    title = textwrap.wrap(node.title, TITLE_WIDTH, break_long_words=False, break_on_hyphens=False)
    rows = [f"<B>{_html(node.id)}</B> · {_html(node.status_label())}",
            "<BR/>".join(_html(line) for line in title)]
    codes = [_html(code) for code in node.dimension_codes()]
    if codes:
        if node.scope and node.kind != "release":
            codes[0] = f'<FONT COLOR="{SCOPE_TEXT_COLOUR[node.scope]}">{codes[0]}</FONT>'
        rows.append(" ".join(codes))
    cells = "".join(f"<TR><TD>{row}</TD></TR>" for row in rows)
    return f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">{cells}</TABLE>>'


def _node_statement(node: Node, indent: str = "  ") -> str:
    shape, style = _SHAPE[node.kind]
    if node.unguarded:
        style += ",dashed"
    style_attr = f'"{style}"' if "," in style else style
    attrs = [f'id="node-{node.id}"', f'class="{node_classes(node)}"', f"label={_card(node)}",
             f"shape={shape}", f"style={style_attr}",
             f'fillcolor="{_FILL[node.status]}"']
    if node.kind == "release":
        attrs += [f'fontcolor="{RELEASE_COLOUR}"', 'fontname="Helvetica-Bold"']
    if node.complexity:
        attrs += [f'color="{COMPLEXITY_COLOUR[node.complexity]}"',
                  f"penwidth={COMPLEXITY_WIDTH[node.complexity]}"]
    if node.amount:
        attrs.append(f"peripheries={AMOUNT_OUTLINES[node.amount]}")
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
                  f'    style="rounded,dashed"; color="{LANE_COLOUR}"; fontcolor="{LIGHT["lane-text"]}";']
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
