"""Self-contained HTML view: pan/zoom graph, click a node for details (atom A3).

The page loads nothing external. Node data travels as JSON in a non-executing
``<script type="application/json">`` block with every ``<`` escaped, and the
modal is filled only via ``textContent``/``createElement``. A Content-Security-
Policy pins the one inline script and the one style block by hash.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from html import escape
from typing import Any

from .model import Plan

_SVG_XMLNS = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"')

_STYLE = """
:root { color-scheme: light dark; --bg: #f8fafc; --fg: #0f172a; --muted: #475569;
  --panel: #ffffff; --border: #cbd5e1; --accent: #2563eb; --backdrop: rgb(15 23 42 / .45); }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0b1120; --fg: #e2e8f0; --muted: #94a3b8; --panel: #1e293b;
    --border: #334155; --accent: #60a5fa; --backdrop: rgb(0 0 0 / .6); }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.caption { color: var(--muted); margin: 0 0 1rem; max-width: 70ch; }
.toolbar { display: flex; gap: .5rem; align-items: center; margin-bottom: .5rem; }
.toolbar span { color: var(--muted); font-size: .85rem; }
button { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--border);
  border-radius: 6px; padding: .3rem .8rem; cursor: pointer; }
button:hover { border-color: var(--accent); }
#viewport { height: 70vh; border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
  background: #ffffff; cursor: grab; touch-action: none; user-select: none; }
#viewport.dragging { cursor: grabbing; }
#viewport svg { display: block; width: 100%; height: 100%; }
#viewport g.node { cursor: pointer; }
#viewport g.node:hover polygon, #viewport g.node:hover path { stroke: var(--accent); stroke-width: 2; }
#viewport g.node:focus { outline: none; }
#viewport g.node:focus-visible polygon, #viewport g.node:focus-visible path { stroke: #2563eb; stroke-width: 3; }
dialog { width: min(36rem, calc(100vw - 32px)); max-height: calc(100vh - 32px); padding: 1.25rem;
  color: var(--fg); background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
dialog::backdrop { background: var(--backdrop); }
dialog header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
dialog h2 { margin: 0; font-size: 1.15rem; }
dialog .node-id { color: var(--muted); font-family: ui-monospace, monospace; font-size: .9rem; }
dialog dl { display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1rem; margin: 1rem 0; }
dialog dt { color: var(--muted); }
dialog dd { margin: 0; }
dialog ul { margin: 0; padding-left: 1.1rem; }
.seam { color: var(--muted); font-size: .85rem; }
.notes { white-space: pre-wrap; margin: 0; padding: .75rem; border-radius: 6px;
  background: var(--bg); border: 1px solid var(--border); }
"""

_SCRIPT = """
"use strict";
(() => {
  const plan = JSON.parse(document.getElementById("plan-data").textContent);
  const viewport = document.getElementById("viewport");
  const svg = viewport.querySelector("svg");
  const dialog = document.getElementById("node-dialog");
  const field = (name) => dialog.querySelector('[data-field="' + name + '"]');

  // ---- pan and zoom, by rewriting the viewBox --------------------------------
  const home = svg.viewBox.baseVal;
  const initial = { x: home.x, y: home.y, w: home.width, h: home.height };
  let view = { ...initial };
  const apply = () => svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
  const unitsPerPixel = () => {
    const box = svg.getBoundingClientRect();
    return Math.max(view.w / box.width, view.h / box.height);
  };
  const toGraph = (clientX, clientY) => {
    const point = new DOMPoint(clientX, clientY);
    return point.matrixTransform(svg.getScreenCTM().inverse());
  };

  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = Math.exp(event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015));
    const width = Math.min(Math.max(view.w * factor, initial.w / 20), initial.w * 5);
    const f = width / view.w;
    const p = toGraph(event.clientX, event.clientY);  // stays under the cursor
    view = { x: p.x - (p.x - view.x) * f, y: p.y - (p.y - view.y) * f, w: view.w * f, h: view.h * f };
    apply();
  }, { passive: false });

  let drag = null;
  let suppressClick = false;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    drag = { x: event.clientX, y: event.clientY, moved: false };
  });
  window.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    viewport.classList.add("dragging");
    const k = unitsPerPixel();
    view.x -= dx * k;
    view.y -= dy * k;
    drag.x = event.clientX;
    drag.y = event.clientY;
    apply();
  });
  window.addEventListener("pointerup", () => {
    if (drag && drag.moved) suppressClick = true;
    drag = null;
    viewport.classList.remove("dragging");
  });
  document.getElementById("reset-view").addEventListener("click", () => {
    view = { ...initial };
    apply();
  });

  // ---- node details modal: textContent / createElement only ------------------
  const fillList = (name, links) => {
    const list = field(name);
    list.replaceChildren();
    if (links.length === 0) {
      const li = document.createElement("li");
      li.textContent = "none";
      list.append(li);
    }
    for (const link of links) {
      const li = document.createElement("li");
      const seam = document.createElement("span");
      seam.className = "seam";
      seam.textContent = " (" + link.seam + " seam)";
      li.append(document.createTextNode(link.id + " — " + plan.nodes[link.id].title), seam);
      list.append(li);
    }
  };
  const openNode = (id) => {
    const node = plan.nodes[id];
    if (!node) return;
    field("id").textContent = node.id;
    field("title").textContent = node.title;
    field("kind").textContent = node.kind;
    field("status").textContent = node.status;
    field("owner").textContent = node.owner || "—";
    field("notes").textContent = node.notes || "—";
    fillList("deps", node.deps);
    fillList("dependents", node.dependents);
    if (!dialog.open) dialog.showModal();
  };
  const nodeIdOf = (group) => group.id.startsWith("node-") ? group.id.slice(5) : null;

  for (const group of svg.querySelectorAll("g.node")) {
    group.setAttribute("tabindex", "0");
    group.setAttribute("role", "button");
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openNode(nodeIdOf(group));
      }
    });
  }
  viewport.addEventListener("click", (event) => {
    if (suppressClick) { suppressClick = false; return; }
    const group = event.target.closest("g.node");
    if (group) openNode(nodeIdOf(group));
  });

  // Esc closes a modal <dialog> natively.
  dialog.querySelector(".close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();  // the backdrop belongs to the dialog box
  });
})();
"""

_DIALOG = """<dialog id="node-dialog" aria-labelledby="dialog-title">
  <header>
    <div><div class="node-id" data-field="id"></div><h2 id="dialog-title" data-field="title"></h2></div>
    <button type="button" class="close" aria-label="Close">Close</button>
  </header>
  <dl>
    <dt>Kind</dt><dd data-field="kind"></dd>
    <dt>Status</dt><dd data-field="status"></dd>
    <dt>Owner</dt><dd data-field="owner"></dd>
    <dt>Depends on</dt><dd><ul data-field="deps"></ul></dd>
    <dt>Dependents</dt><dd><ul data-field="dependents"></ul></dd>
  </dl>
  <p class="notes" data-field="notes"></p>
</dialog>"""


def _sha256(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


def plan_data(plan: Plan) -> dict[str, Any]:
    """The JSON payload: every node with its deps and its dependents, keyed by id."""
    dependents: dict[str, list[dict[str, str]]] = {n.id: [] for n in plan.nodes}
    for edge in plan.edges():
        dependents[edge.source].append({"id": edge.target, "seam": edge.seam})
    return {"nodes": {
        n.id: {"id": n.id, "title": n.title, "kind": n.kind, "status": n.status,
               "owner": n.owner, "notes": n.notes,
               "deps": [{"id": d.id, "seam": d.seam} for d in n.deps],
               "dependents": dependents[n.id]}
        for n in plan.nodes
    }}


def build_html(plan: Plan, svg: str) -> str:
    """One self-contained page; ``svg`` is ``render_svg(plan)`` output, inlined as is."""
    data = json.dumps(plan_data(plan), ensure_ascii=False).replace("<", "\\u003c")
    # xmlns is redundant for SVG inlined in HTML; dropping it keeps the page free of URLs.
    inline_svg = _SVG_XMLNS.sub("", svg)
    csp = (f"default-src 'none'; script-src {_sha256(_SCRIPT)}; style-src {_sha256(_STYLE)}; "
           "base-uri 'none'; form-action 'none'")
    title = escape(plan.title)
    caption = f'<p class="caption">{escape(plan.caption)}</p>\n' if plan.caption else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{title}</h1>
{caption}<div class="toolbar"><button type="button" id="reset-view">Reset view</button>
<span>Drag to pan, scroll to zoom, click a node for details.</span></div>
<div id="viewport">
{inline_svg}</div>
{_DIALOG}
<script type="application/json" id="plan-data">{data}</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""
