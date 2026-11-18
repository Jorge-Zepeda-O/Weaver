"""Graphviz export: DOT source and inline-ready SVG (atom A2).

Every node statement carries ``id="node-<id>"``, so the SVG group for node X
is ``<g id="node-X" class="node">``. That id is the contract with the HTML view
(A3) and the PDF view (A5).

Encoding: shape = kind, fill = status, edge style = seam, lane = group, text
colour = scope, border colour and weight = complexity, outline count = amount,
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
RULE_COLOUR = LIGHT["rule"]


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
    """B4, laid out per A3-7 (layout C): the header (bold id, status) across the top over a
    rule; below it the wrapped title, and the codes in a right column behind a divider.
    Marker and letter sit in separate cells, so the letters line up although the markers
    differ in width."""
    title = "<BR/>".join(_html(line) for line in textwrap.wrap(
        node.title, TITLE_WIDTH, break_long_words=False, break_on_hyphens=False))
    codes = node.dimension_codes()
    header = f"<B>{_html(node.id)}</B> · {_html(node.status_label())}"
    table = f'<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" COLOR="{RULE_COLOUR}">'
    if not codes:
        return f"<{table}<TR><TD>{header}</TD></TR><HR/><TR><TD>{title}</TD></TR></TABLE>>"
    rows = [f'<TD>{_html(code[0])}</TD><TD ALIGN="LEFT">{_html(code[1:])}</TD>' for code in codes]
    rows[0] = f'<TD ROWSPAN="{len(codes)}">{title}</TD><VR/>' + rows[0]
    body = "".join(f"<TR>{row}</TR>" for row in rows)
    return f'<{table}<TR><TD COLSPAN="3">{header}</TD></TR><HR/>{body}</TABLE>>'


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
    elif node.scope:
        attrs.append(f'fontcolor="{SCOPE_TEXT_COLOUR[node.scope]}"')
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
    return _NODE_GROUP.sub(_centred_node, svg).strip() + "\n"


# A3-6: Graphviz 2.43 draws an HTML label as one <text> per run, each anchored at its start
# with widths measured in the font Graphviz found. A browser that draws a narrower or wider
# face shifts every line sideways. Each line becomes one middle-anchored <text>; runs that
# differ (the bold id) become <tspan>s inside it.
# A3-7: the card's rules are drawn as flat polygons, and they give every centre. The header
# rule spans the table, so its middle centres the header; the title centres between the
# rule's left end and the divider; a marker centres between the divider and its letter, and
# the letters keep their shared start. Without rules, everything centres on the shape.
_NODE_GROUP = re.compile(r'(<g id="node-[^"]*" class="node[^"]*">)(.*?)(</g>)', re.S)
_SHAPE_COORDS = re.compile(r'<(?:polygon|path) [^>]*?(?:points|d)="([^"]*)"')
_POLYGON = re.compile(r'<polygon ([^>]*?)points="([^"]*)"')
_TEXT_RUN = re.compile(r'<text ([^>]*)>([^<]*)</text>\n?')
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')
_POSITION = ("text-anchor", "x")

Run = tuple[dict[str, str], str]


def _coords(points: str) -> tuple[list[float], list[float]]:
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", points)]
    return numbers[0::2], numbers[1::2]


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _centred_node(match: re.Match) -> str:
    head, body, tail = match.groups()
    shape = _SHAPE_COORDS.search(body)
    runs = list(_TEXT_RUN.finditer(body))
    if shape is None or not runs:
        return match.group(0)
    xs, _ = _coords(shape.group(1))
    header_centre = title_centre = (min(xs) + max(xs)) / 2
    rule_y = divider = None
    for polygon in _POLYGON.finditer(body):
        px, py = _coords(polygon.group(2))
        if len(set(py)) == 1 and rule_y is None:
            rule_y, header_centre = py[0], (min(px) + max(px)) / 2
            title_centre, rule_left = header_centre, min(px)
        elif len(set(px)) == 1 and divider is None:
            divider = px[0]
    if rule_y is not None and divider is not None:
        title_centre = (rule_left + divider) / 2

    lines: dict[tuple[bool, str], list[Run]] = {}
    for run in runs:
        attrs = dict(_ATTR.findall(run.group(1)))
        is_code = divider is not None and float(attrs["x"]) > divider
        lines.setdefault((is_code, attrs["y"]), []).append((attrs, run.group(2)))
    texts = []
    for (is_code, y), line in lines.items():
        if is_code:
            texts.append(_code_row(line, divider))
        else:
            above_rule = rule_y is None or float(y) < rule_y
            texts.append(_centred_line(line, _number(header_centre if above_rule else title_centre)))
    rest = _POLYGON.sub(_marked_rule, body[runs[-1].end():])
    return head + body[:runs[0].start()] + "".join(texts) + rest + tail


def _marked_rule(match: re.Match) -> str:
    """A flat polygon is a card rule: classed, so the page's shape styles pass it by."""
    xs, ys = _coords(match.group(2))
    if len(set(xs)) == 1 or len(set(ys)) == 1:
        return f'<polygon class="rule" {match.group(1)}points="{match.group(2)}"'
    return match.group(0)


def _code_row(line: list[Run], divider: float) -> str:
    """A marker centred between the divider and its letter; the letter left as drawn."""
    if len(line) != 2:
        return "".join(_text(attrs, content) for attrs, content in line)
    marker, letter = sorted(line, key=lambda run: float(run[0]["x"]))
    centre = _number((divider + float(letter[0]["x"])) / 2)
    return _centred_line([marker], centre) + _text(*letter)


def _text(attrs: dict[str, str], content: str) -> str:
    return "<text " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + f">{content}</text>\n"


def _centred_line(line: list[Run], centre: str) -> str:
    first = line[0][0]
    common = {k: v for k, v in first.items()
              if k not in _POSITION and all(attrs.get(k) == v for attrs, _ in line)}
    outer = " ".join([f'text-anchor="middle" x="{centre}"'] + [f'{k}="{v}"' for k, v in common.items()])
    if len(line) == 1:
        return f"<text {outer}>{line[0][1]}</text>\n"
    spans = []
    for attrs, content in line:
        own = " ".join(f'{k}="{v}"' for k, v in attrs.items() if k not in _POSITION and k not in common)
        spans.append(f"<tspan {own}>{content}</tspan>" if own else f"<tspan>{content}</tspan>")
    return f"<text {outer}>{''.join(spans)}</text>\n"
