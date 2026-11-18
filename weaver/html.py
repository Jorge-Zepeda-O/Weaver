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

from .dot import (_FILL, AMOUNT_OUTLINES, COMPLEXITY_COLOUR, COMPLEXITY_WIDTH, RELEASE_COLOUR,
                  SCOPE_TEXT_COLOUR)
from .model import DIMENSION_MARKER, DIMENSIONS, STATUS_SYMBOL, STATUSES, Plan, overlaps
from .tokens import LIGHT, css_variables

_SVG_XMLNS = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"')

_SCOPES = ("I", "L", "P", "U", "G", "unknown")
_COMPLEXITIES = ("T", "E", "M", "H", "N", "unknown")


def _graph_rules() -> str:
    """B2: the page's stylesheet drives the graph through the SVG classes (B1) and the
    tokens (B0). Graphviz's own attributes stay as the fallback for the standalone SVG and
    the PDF. Placed before the hover and focus rules, which win at equal specificity."""
    rules = (
        # Only the filled shape: stacked outlines (amount, D-16) are fill="none" and stay hollow.
        [f'#viewport g.node.status-{s} :is(polygon, path):not([fill="none"], .rule) '
         f"{{ fill: var(--wv-status-{s}); }}" for s in STATUSES]
        + [f"#viewport g.node.complexity-{c} :is(polygon, path):not(.rule) "
           f"{{ stroke: var(--wv-complexity-{c}); }}" for c in _COMPLEXITIES]
        # Scope colours the whole text (D-18); a release's text stays purple (D-15).
        + [f"#viewport g.node.scope-{c}:not(.kind-release) text "
           f"{{ fill: var(--wv-scope-text-{c}); }}" for c in _SCOPES]
        + ["#viewport g.node.kind-release text { fill: var(--wv-release); font-weight: bold; }",
           # The card's rules (A3-7) stay one quiet colour, whatever the node's status or border.
           "#viewport g.node polygon.rule { fill: var(--wv-rule); stroke: var(--wv-rule); }",
           # The overlap mark (A3-4) keeps its alert colour inside any scope's text.
           "#viewport g.node text tspan.alert { fill: var(--wv-alert); }",
           "#viewport g.cluster.lane > :is(polygon, path) { stroke: var(--wv-lane); }",
           "#viewport g.cluster.lane > text { fill: var(--wv-lane-text); }"])
    return "\n".join(rules) + "\n"


_STYLE = css_variables() + _graph_rules() + """
:root { color-scheme: light dark; --wv-backdrop: rgb(15 23 42 / .45); }
@media (prefers-color-scheme: dark) {
  :root { --wv-backdrop: rgb(0 0 0 / .6); }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--wv-bg); color: var(--wv-fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.caption { color: var(--wv-muted); margin: 0 0 1rem; max-width: 70ch; }
.toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-bottom: .5rem; }
.toolbar span { color: var(--wv-muted); font-size: .85rem; }
#find { font: inherit; width: 9rem; color: var(--wv-fg); background: var(--wv-panel);
  border: 1px solid var(--wv-border); border-radius: 6px; padding: .3rem .5rem; }
/* A3-5: the node a link or the find box names. .rule is the card's rules (A3-7, lane graph). */
#viewport g.node.found { filter: drop-shadow(0 0 6px var(--wv-accent)); }
#viewport g.node.found :is(polygon, path):not(.rule) { stroke: var(--wv-accent); stroke-width: 4; }
button { font: inherit; color: var(--wv-fg); background: var(--wv-panel); border: 1px solid var(--wv-border);
  border-radius: 6px; padding: .3rem .8rem; cursor: pointer; }
button:hover { border-color: var(--wv-accent); }
#viewport { height: 70vh; border: 1px solid var(--wv-border); border-radius: 8px; overflow: hidden;
  background: var(--wv-canvas); cursor: grab; touch-action: none; user-select: none; }
#viewport.dragging { cursor: grabbing; }
#viewport svg { display: block; width: 100%; height: 100%; }
#viewport g.node { cursor: pointer; }
#viewport g.node:hover :is(polygon, path):not(.rule) { stroke: var(--wv-accent); stroke-width: 2; }
#viewport g.node:focus { outline: none; }
#viewport g.node:focus-visible :is(polygon, path):not(.rule) { stroke: var(--wv-focus); stroke-width: 3; }
dialog { width: min(36rem, calc(100vw - 32px)); max-height: calc(100vh - 32px); padding: 1.25rem;
  color: var(--wv-fg); background: var(--wv-panel); border: 1px solid var(--wv-border); border-radius: 10px; }
dialog::backdrop { background: var(--wv-backdrop); }
dialog header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
dialog h2 { margin: 0; font-size: 1.15rem; }
dialog .node-id { color: var(--wv-muted); font-family: ui-monospace, monospace; font-size: .9rem; }
dialog dl { display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1rem; margin: 1rem 0; }
dialog dt { color: var(--wv-muted); }
dialog dd { margin: 0; }
dialog ul { margin: 0; padding-left: 1.1rem; }
.seam { color: var(--wv-muted); font-size: .85rem; }
.goal { margin: 0 0 .5rem; max-width: 70ch; }
#legend { margin-top: .75rem; color: var(--wv-muted); font-size: .85rem; }
#legend summary { cursor: pointer; color: var(--wv-fg); }
#legend dl { display: grid; grid-template-columns: max-content 1fr; gap: .4rem 1rem; margin: .5rem 0 0; }
#legend dt { color: var(--wv-fg); }
#legend dd { margin: 0; display: flex; flex-wrap: wrap; gap: .25rem .9rem; }
#legend svg { vertical-align: middle; margin-right: .25rem; }
.notes { white-space: pre-wrap; margin: 0; padding: .75rem; border-radius: 6px;
  background: var(--wv-bg); border: 1px solid var(--wv-border); }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .4rem; margin: 1rem 0 .25rem; }
.stat { min-width: 0; padding: .3rem .5rem; border: 1px solid var(--wv-border); border-radius: 6px;
  overflow-wrap: anywhere; }
.stat-label { display: block; color: var(--wv-muted); font-size: .75rem; }
.stat-value { font-weight: 600; }
.stat[class*="status-"] { color: var(--wv-ink); }
.stat[class*="status-"] .stat-label { color: inherit; opacity: .75; }
.stat.kind-release { color: var(--wv-release); }
.stat.kind-release .stat-value { font-weight: 800; }
""" + "".join(
    # B5: each stats cell takes its value's colour from the tokens; the page's CSP pins this
    # sheet by hash, so the colours live here as classes, never as style="" attributes.
    [f".stat.status-{s} {{ background: var(--wv-status-{s}); }}\n" for s in STATUSES]
    + [f".stat.scope-{c} {{ border-left: 4px solid var(--wv-scope-{c}); }}\n"
       for c in _SCOPES]
    + [f".stat.complexity-{c} {{ border-left: 4px solid var(--wv-complexity-{c}); }}\n"
       for c in _COMPLEXITIES])

# The Task Dimension glyphs, one per value. Emoji, so the HTML view only: WeasyPrint
# drops them, which is why the node, Markdown and PDF use the markers and codes instead.
GLYPHS: dict[str, dict[str, str]] = {
    "scope": dict(zip("ILPUG?", "🟦🟩🟨🟧🟥❓")),
    "amount": dict(zip("1FNBS?", "📄📑📚📦🌊❓")),
    "complexity": dict(zip("TEMHN?", "⚪⬜🔶🔺💥❓")),
}

# DOM-free panel core: a node in, the stats table's six cells out (text and class).
# Kept apart from the page wiring so tests can run it under Node.
_PANEL = """
const panelStats = (node, plan) => {
  const cells = [
    { name: "kind", label: "Kind", text: node.kind, cls: "kind-" + node.kind },
    { name: "status", label: "Status", text: node.status_label, cls: "status-" + node.status },
    { name: "group", label: "Group", text: node.group || "—", cls: "" },
  ];
  for (const name of ["scope", "amount", "complexity"]) {
    const code = node[name], marker = plan.markers[name];
    const label = name[0].toUpperCase() + name.slice(1);
    cells.push(code
      ? { name, label, cls: name + "-" + (code === "?" ? "unknown" : code),
          text: plan.glyphs[name][code] + " " + marker + code + " · " + plan.terms[name][code] }
      : { name, label, cls: "", text: marker + " unassessed" });
  }
  return cells;
};
"""

# DOM-free gesture core: pointer events in, pan/zoom calls and a click verdict out.
# Kept apart from the page wiring so tests can run it under Node.
_GESTURES = """
"use strict";
const makeGestures = ({ pan, zoom }) => {
  // Movement below this many pixels is a wobbly click, not a drag; fingers wobble more.
  const slopFor = (type) => (type === "touch" ? 10 : 4);
  const pointers = new Map();  // pointerId -> last seen {x, y}
  let start = null;            // where the single-pointer gesture began, with its slop
  let pinch = null;            // last {dist, mx, my} of a two-pointer gesture
  let moved = false;           // the current gesture panned or pinched: it is not a click

  const span = () => {
    const [a, b] = [...pointers.values()];
    return { dist: Math.hypot(b.x - a.x, b.y - a.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
  };

  return {
    down(e) {
      // A primary press starts a new gesture. Clearing here, not on click, means a
      // drag that ends with no click cannot eat the next tap, and a pointer whose
      // pointerup was lost cannot pair with this one into a phantom pinch.
      if (e.primary) { pointers.clear(); moved = false; pinch = null; }
      pointers.set(e.id, { x: e.x, y: e.y });
      if (pointers.size === 1) start = { x: e.x, y: e.y, slop: slopFor(e.type) };
      if (pointers.size === 2) { pinch = span(); moved = true; }
    },
    move(e) {
      const last = pointers.get(e.id);
      if (!last) return;
      if (pinch) {
        last.x = e.x;
        last.y = e.y;
        const now = span();
        if (pinch.dist > 0 && now.dist > 0) zoom(pinch.dist / now.dist, now.mx, now.my);
        pan(now.mx - pinch.mx, now.my - pinch.my);
        pinch = now;
        return;
      }
      if (pointers.size !== 1) return;
      if (!moved && Math.hypot(e.x - start.x, e.y - start.y) < start.slop) return;
      moved = true;
      pan(e.x - last.x, e.y - last.y);
      last.x = e.x;
      last.y = e.y;
    },
    up(e) {
      pointers.delete(e.id);
      if (pointers.size < 2) pinch = null;
    },
    clickAllowed: () => !moved,
  };
};
"""

# DOM-free find core (A3-5): a query (a URL hash or typed text) in, the node to show out;
# marking and moving the view are handed in, so tests run it under Node with fakes, and
# v0.4's outline buttons can reuse it. An unknown id changes nothing and throws nothing.
_FIND = """
const findNode = (query, ids) => {
  let text = String(query ?? "").trim().replace(/^#/, "");
  try { text = decodeURIComponent(text).trim(); } catch { return null; }
  if (!text) return null;
  if (ids.includes(text)) return text;
  const folded = ids.filter((id) => id.toLowerCase() === text.toLowerCase());
  return folded.length === 1 ? folded[0] : null;
};

// The view that shows box: centred on it, zoomed in to about five node widths, never out
// from a closer look the reader chose, never so close that the node does not fit, and
// within the zoom limits. The view keeps its aspect ratio.
const focusView = (view, box, limits) => {
  const aspect = view.h / view.w;
  const fit = Math.max(box.width, box.height / aspect) * 1.5;
  const wanted = Math.max(Math.min(view.w, box.width * 5), fit);
  const w = Math.min(Math.max(wanted, limits.min), limits.max);
  const h = w * aspect;
  return { x: box.x + box.width / 2 - w / 2, y: box.y + box.height / 2 - h / 2, w, h };
};

const makeFinder = ({ ids, boxOf, getView, setView, mark, limits }) => {
  let current = null;
  return {
    go(query) {
      const id = findNode(query, ids);
      if (id === null) return null;
      if (current !== null && current !== id) mark(current, false);
      mark(id, true);
      current = id;
      setView(focusView(getView(), boxOf(id), limits));
      return id;
    },
  };
};
"""

_SCRIPT = _GESTURES + _PANEL + _FIND + """
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

  // factor = new width / old width; the graph point under (clientX, clientY) stays put.
  const zoomAt = (factor, clientX, clientY) => {
    const width = Math.min(Math.max(view.w * factor, initial.w / 20), initial.w * 5);
    const f = width / view.w;
    const p = toGraph(clientX, clientY);
    view = { x: p.x - (p.x - view.x) * f, y: p.y - (p.y - view.y) * f, w: view.w * f, h: view.h * f };
    apply();
  };
  const panBy = (dx, dy) => {
    const k = unitsPerPixel();
    view.x -= dx * k;
    view.y -= dy * k;
    apply();
    viewport.classList.add("dragging");
  };

  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomAt(Math.exp(event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015)), event.clientX, event.clientY);
  }, { passive: false });

  const gestures = makeGestures({ pan: panBy, zoom: zoomAt });
  const pointer = (event) => ({ id: event.pointerId, x: event.clientX, y: event.clientY,
                                type: event.pointerType, primary: event.isPrimary });
  viewport.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    gestures.down(pointer(event));
  });
  window.addEventListener("pointermove", (event) => gestures.move(pointer(event)));
  const release = (event) => {
    gestures.up(pointer(event));
    viewport.classList.remove("dragging");
  };
  window.addEventListener("pointerup", release);
  window.addEventListener("pointercancel", release);
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
      li.append(document.createTextNode(link.id + " — " + plan.nodes[link.id].title));
      if (link.seam) {
        const seam = document.createElement("span");
        seam.className = "seam";
        seam.textContent = " (" + link.seam + " seam)";
        li.append(seam);
      }
      list.append(li);
    }
  };
  // A3-4: the files this node shares with another lane, and why, where acknowledged.
  const fillOverlaps = (overlaps) => {
    const list = field("overlaps");
    list.replaceChildren();
    if (overlaps.length === 0) {
      const li = document.createElement("li");
      li.textContent = "none";
      list.append(li);
    }
    for (const overlap of overlaps) {
      const li = document.createElement("li");
      li.textContent = "⚠ " + overlap.file + ": with " + overlap.other + " — " + plan.nodes[overlap.other].title;
      if (overlap.reason) {
        const reason = document.createElement("span");
        reason.className = "seam";
        reason.textContent = " (acknowledged: " + overlap.reason + ")";
        li.append(reason);
      }
      list.append(li);
    }
  };
  const openNode = (id) => {
    const node = plan.nodes[id];
    if (!node) return;
    field("id").textContent = node.id;
    field("title").textContent = node.title;
    for (const stat of panelStats(node, plan)) {
      const cell = dialog.querySelector('[data-stat="' + stat.name + '"]');
      cell.className = stat.cls ? "stat " + stat.cls : "stat";
      cell.querySelector(".stat-value").textContent = stat.text;
    }
    field("verify").textContent = node.verify || (node.unguarded ? "none — unguarded merge" : "—");
    field("decisions").textContent = node.decisions.length ? node.decisions.join(", ") : "—";
    field("notes").textContent = node.notes || "—";
    fillList("deps", node.deps);
    fillList("dependents", node.dependents);
    fillList("reworks", node.reworks);
    fillList("reworked_by", node.reworked_by);
    fillOverlaps(node.overlaps);
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
    if (!gestures.clickAllowed()) return;
    const group = event.target.closest("g.node");
    if (group) openNode(nodeIdOf(group));
  });

  // ---- find by id (A3-5): PLAN.html#B4, or the find box ----------------------
  const ids = Object.keys(plan.nodes);
  const groupOf = (id) => document.getElementById("node-" + id);
  const finder = makeFinder({
    ids,
    // The node's box in the SVG's own units: its local box, through its transform.
    boxOf: (id) => {
      const group = groupOf(id), local = group.getBBox();
      const matrix = svg.getScreenCTM().inverse().multiply(group.getScreenCTM());
      const a = new DOMPoint(local.x, local.y).matrixTransform(matrix);
      const b = new DOMPoint(local.x + local.width, local.y + local.height).matrixTransform(matrix);
      return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
               width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) };
    },
    getView: () => view,
    setView: (next) => { view = next; apply(); },
    mark: (id, on) => groupOf(id).classList.toggle("found", on),
    limits: { min: initial.w / 20, max: initial.w * 5 },
  });
  const findInput = document.getElementById("find");
  const findStatus = document.getElementById("find-status");
  findInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const id = findNode(findInput.value, ids);
    findStatus.textContent = id === null ? "No node " + findInput.value.trim() + "." : "";
    if (id === null) return;
    // The hash makes the find a link; the same hash again fires no hashchange.
    if (findNode(location.hash, ids) === id) finder.go(id);
    else location.hash = id;
  });
  window.addEventListener("hashchange", () => finder.go(location.hash));
  if (location.hash) finder.go(location.hash);

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
  <div class="stats">""" + "".join(
    f'<div class="stat" data-stat="{name}"><span class="stat-label">{name.capitalize()}</span>'
    f'<span class="stat-value"></span></div>'
    for name in ("kind", "status", "group", "scope", "amount", "complexity")) + """</div>
  <dl>
    <dt>Verified by</dt><dd data-field="verify"></dd>
    <dt>Decisions</dt><dd data-field="decisions"></dd>
    <dt>Depends on</dt><dd><ul data-field="deps"></ul></dd>
    <dt>Dependents</dt><dd><ul data-field="dependents"></ul></dd>
    <dt>Reworks</dt><dd><ul data-field="reworks"></ul></dd>
    <dt>Reworked by</dt><dd><ul data-field="reworked_by"></ul></dd>
    <dt>Overlaps</dt><dd><ul data-field="overlaps"></ul></dd>
  </dl>
  <p class="notes" data-field="notes"></p>
</dialog>"""


def _sha256(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


def plan_data(plan: Plan) -> dict[str, Any]:
    """The JSON payload: every node with its deps and its dependents, keyed by id,
    plus the names of the dimension codes."""
    dependents: dict[str, list[dict[str, str]]] = {n.id: [] for n in plan.nodes}
    for edge in plan.edges():
        dependents[edge.source].append({"id": edge.target, "seam": edge.seam})
    reworked_by: dict[str, list[dict[str, str]]] = {n.id: [] for n in plan.nodes}
    for n in plan.nodes:  # A3-11: the fixed node names its fixes
        for target in n.reworks:
            reworked_by[target].append({"id": n.id})
    shared: dict[str, list[dict[str, str]]] = {n.id: [] for n in plan.nodes}
    for overlap in overlaps(plan):  # A3-4: each side lists the other
        for here, other in ((overlap.a, overlap.b), (overlap.b, overlap.a)):
            shared[here].append({"file": overlap.file, "other": other, "reason": overlap.reason})
    return {"terms": DIMENSIONS, "markers": DIMENSION_MARKER, "glyphs": GLYPHS, "nodes": {
        n.id: {"id": n.id, "title": n.title, "kind": n.kind, "status": n.status,
               "status_label": n.status_label(),
               "group": n.group, "notes": n.notes, "scope": n.scope, "amount": n.amount,
               "complexity": n.complexity, "verify": n.verify, "decisions": list(n.decisions),
               "unguarded": n.unguarded,
               "deps": [{"id": d.id, "seam": d.seam} for d in n.deps],
               "dependents": dependents[n.id], "overlaps": shared[n.id],
               "reworks": [{"id": r} for r in n.reworks], "reworked_by": reworked_by[n.id]}
        for n in plan.nodes
    }}


def _swatch(shape: str = "box", fill: str = LIGHT["canvas"], stroke: str = LIGHT["ink"],
            width: str = "1", dashed: bool = False, dotted: bool = False) -> str:
    """A small inline SVG key. Presentation attributes only: the CSP refuses style=""."""
    dash = ' stroke-dasharray="3 2"' if dashed else ' stroke-dasharray="1 2"' if dotted else ""
    paint = f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash}'
    body = {
        "box": f'<rect x="2" y="2" width="18" height="12" rx="3" {paint}/>',
        "hexagon": f'<polygon points="2,8 6,2 16,2 20,8 16,14 6,14" {paint}/>',
        "line": f'<line x1="1" y1="8" x2="21" y2="8" stroke="{stroke}" stroke-width="1.5"{dash}/>',
        "octagon": f'<polygon points="7,1 15,1 21,5 21,11 15,15 7,15 1,11 1,5" {paint}/>',
    }[shape]
    return f'<svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">{body}</svg>'


def _text_swatch(colour: str) -> str:
    """Scope's key: a sample of text in its colour, as the node's text is drawn."""
    return (f'<svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">'
            f'<text x="11" y="12.5" text-anchor="middle" font-size="12" font-weight="bold" '
            f'font-family="sans-serif" fill="{colour}">Aa</text></svg>')


def _outlines_swatch(count: int) -> str:
    """D-16's key: one rectangle per outline, nested like Graphviz's peripheries."""
    rects = "".join(
        f'<rect x="{1 + 1.4 * i:g}" y="{1 + 1.4 * i:g}" width="{20 - 2.8 * i:g}" '
        f'height="{14 - 2.8 * i:g}" rx="2" fill="none" stroke="{LIGHT["ink"]}" stroke-width="0.8"/>'
        for i in range(count))
    return f'<svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">{rects}</svg>'


def _legend() -> str:
    def items(entries: list[tuple[str, str]]) -> str:
        return "".join(f"<span>{swatch}{escape(text)}</span>" for swatch, text in entries)

    rows = [
        ("Status (symbol, fill)", items([(_swatch(fill=c), f"{STATUS_SYMBOL[s]} {s}")
                                         for s, c in _FILL.items()])),
        ("Kind (shape)", items([(_swatch(), "atom"), (_swatch("hexagon"), "merge"),
                                (_swatch("hexagon", dashed=True), "unguarded merge (no verify)"),
                                (_swatch("octagon", stroke=RELEASE_COLOUR), "release")])),
        ("Seam (edge)", items([(_swatch("line"), "build seam"),
                               (_swatch("line", dashed=True), "runtime seam"),
                               (_swatch("line", stroke=LIGHT["rework"], dotted=True),
                                "rework (from the fixed node to its fix)")])),
        ("Scope (text colour)", items([(_text_swatch(SCOPE_TEXT_COLOUR[c]), f"{GLYPHS['scope'][c]} {c} {n}")
                                       for c, n in DIMENSIONS["scope"].items()])),
        ("Complexity (border colour, weight)",
         items([(_swatch(stroke=COMPLEXITY_COLOUR[c], width=COMPLEXITY_WIDTH[c]), f"{GLYPHS['complexity'][c]} {c} {n}")
                for c, n in DIMENSIONS["complexity"].items()])),
        ("Amount (outlines)", items([(_outlines_swatch(int(AMOUNT_OUTLINES[c])), f"{GLYPHS['amount'][c]} {c} {n}")
                                     for c, n in DIMENSIONS["amount"].items()])),
        ("Overlap (⚠)", escape("this node and one in another lane touch the same file, with nothing "
                               "ordering them; the panel names the file and any acknowledged reason")),
        ("In each node", escape("↕scope (reach) ↔amount (breadth) ⤓complexity (depth); - unassessed, "
                                "? assessed but unknowable (ranks worst)")),
    ]
    body = "".join(f"<dt>{escape(term)}</dt><dd>{dd}</dd>" for term, dd in rows)
    return f'<details id="legend"><summary>Legend</summary><dl>{body}</dl></details>'


def build_html(plan: Plan, svg: str) -> str:
    """One self-contained page; ``svg`` is ``render_svg(plan)`` output, inlined as is."""
    data = json.dumps(plan_data(plan), ensure_ascii=False).replace("<", "\\u003c")
    # xmlns is redundant for SVG inlined in HTML; dropping it keeps the page free of URLs.
    inline_svg = _SVG_XMLNS.sub("", svg)
    csp = (f"default-src 'none'; script-src {_sha256(_SCRIPT)}; style-src {_sha256(_STYLE)}; "
           "base-uri 'none'; form-action 'none'")
    title = escape(plan.title)
    goal = f'<p class="goal"><strong>Goal:</strong> {escape(plan.goal)}</p>\n' if plan.goal else ""
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
{goal}{caption}<div class="toolbar"><button type="button" id="reset-view">Reset view</button>
<input type="search" id="find" placeholder="Find an id" aria-label="Find a node by id"
 autocomplete="off" spellcheck="false"><span id="find-status" role="status"></span>
<span>Drag to pan, scroll or pinch to zoom, click a node for details.</span></div>
<div id="viewport">
{inline_svg}</div>
{_legend()}
{_DIALOG}
<script type="application/json" id="plan-data">{data}</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""
