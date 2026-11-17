"""PDF view of a plan (atom A5): the graph, its caption, then the field notes.

The static stand-in for the HTML modals. Consumes the SVG produced by
``dot.render_svg`` (a runtime seam: only its output, never its code).
WeasyPrint is imported lazily so the other views work without it.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from .model import Plan, dimension_key
from .tokens import css_variables

_CSS = css_variables(dark=False) + """
@page { size: A4 landscape; margin: 14mm; }
body { font-family: sans-serif; font-size: 10pt; color: var(--wv-print-ink); }
h1 { font-size: 16pt; margin: 0 0 4mm; }
.graph { text-align: center; }
.graph img { max-width: 100%; max-height: 140mm; }
.goal { margin: 0 0 3mm; }
.caption { font-style: italic; margin: 3mm 0 0; }
.key { color: var(--wv-print-muted); font-size: 8.5pt; margin: 2mm 0 0; }
.notes { page-break-before: always; }
.note { margin: 0 0 5mm; page-break-inside: avoid; }
.note h2 { font-size: 11pt; margin: 0 0 1mm; }
.meta { color: var(--wv-print-muted); margin: 0 0 1mm; }
.body { white-space: pre-wrap; margin: 0; }
"""


def build_pdf(plan: Plan, svg: str, out_path: str | Path) -> None:
    from weasyprint import HTML  # lazy: only this view needs it

    HTML(string=_page(plan, svg)).write_pdf(str(out_path))


def _page(plan: Plan, svg: str) -> str:
    image = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{escape(plan.title)}</title><style>{_CSS}</style></head><body>",
        f"<h1>{escape(plan.title)}</h1>",
        f"<p class='goal'>Goal: {escape(plan.goal)}</p>" if plan.goal else "",
        f"<div class='graph'><img alt='plan graph' src='data:image/svg+xml;base64,{image}'></div>",
    ]
    if plan.caption:
        parts.append(f"<p class='caption'>{escape(plan.caption)}</p>")
    parts.append("<p class='key'>" + "<br>".join(escape(k) for k in dimension_key()) + "</p>")

    parts.append("<section class='notes'><h1>Field notes</h1>")
    for node in plan.nodes:
        deps = ", ".join(d.id if d.seam == "build" else f"{d.id} (runtime)" for d in node.deps)
        verify = f"verify: {node.verify}" if node.verify else ("unguarded" if node.unguarded else "")
        decisions = "decisions: " + ", ".join(node.decisions) if node.decisions else ""
        meta = " · ".join(filter(None, [node.kind, node.status, node.group,
                                        node.dimension_label(), verify, decisions,
                                        f"depends on {deps}" if deps else ""]))
        parts.append(
            f"<div class='note'><h2>{escape(node.id)}: {escape(node.title)}</h2>"
            f"<p class='meta'>{escape(meta)}</p>"
            f"<p class='body'>{escape(node.notes.strip())}</p></div>"
        )
    parts.append("</section></body></html>")
    return "".join(parts)
