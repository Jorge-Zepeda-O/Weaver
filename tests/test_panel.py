"""B5: the details panel opens on a stats table.

Two rows of three cells, Kind | Status | Group over Scope | Amount | Complexity,
each with its icon and a class the stylesheet colours from the tokens. The cell
contents come from a DOM-free core (``weaver.html._PANEL``), run here under Node.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest

from weaver import parse_plan
from weaver.html import build_html, plan_data

NODE = shutil.which("node")

_DRIVER = """
const { plan, id } = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(panelStats(plan.nodes[id], plan)));
"""

PLAN = parse_plan({"plan": {"schema": 2, "title": "T"}, "node": [
    {"id": "a", "title": "A", "status": "done", "group": "main",
     "scope": "L", "amount": "F", "complexity": "M"},
    {"id": "b", "title": "B", "scope": "?", "deps": ["a"]},
    {"id": "r", "title": "R", "kind": "release", "verify": "tag", "complexity": "H",
     "amount": "1", "deps": ["b"]},
]})


def stats(node_id: str) -> list[dict]:
    from weaver.html import _PANEL  # deferred: RED until the core exists
    payload = json.dumps({"plan": plan_data(PLAN), "id": node_id})
    result = subprocess.run([NODE, "-e", _PANEL + _DRIVER], input=payload,
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "Node.js not installed: the panel core is untested")
class TestPanelStats(unittest.TestCase):
    def test_six_cells_in_two_rows_of_three(self):
        self.assertEqual([c["name"] for c in stats("a")],
                         ["kind", "status", "group", "scope", "amount", "complexity"])

    def test_a_fully_assessed_node(self):
        self.assertEqual([(c["label"], c["text"], c["cls"]) for c in stats("a")], [
            ("Kind", "atom", "kind-atom"),
            ("Status", "✓ done", "status-done"),
            ("Group", "main", ""),
            ("Scope", "🟩 ↕L · local", "scope-L"),
            ("Amount", "📑 ↔F · few", "amount-F"),
            ("Complexity", "🔶 ⤓M · moderate", "complexity-M"),
        ])

    def test_unknowable_and_unassessed(self):
        cells = {c["name"]: (c["text"], c["cls"]) for c in stats("b")}
        self.assertEqual(cells["scope"], ("❓ ↕? · unknowable", "scope-unknown"))
        self.assertEqual(cells["amount"], ("↔ unassessed", ""))
        self.assertEqual(cells["group"], ("—", ""))

    def test_release(self):
        cells = {c["name"]: (c["text"], c["cls"]) for c in stats("r")}
        self.assertEqual(cells["kind"], ("release", "kind-release"))
        self.assertEqual(cells["complexity"], ("🔺 ⤓H · hard", "complexity-H"))
        self.assertEqual(cells["amount"], ("📄 ↔1 · one", "amount-1"))


class TestPanelPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = build_html(PLAN, "<svg></svg>")

    def test_payload_carries_the_glyphs_and_markers(self):
        data = plan_data(PLAN)
        self.assertEqual(data["markers"], {"scope": "↕", "amount": "↔", "complexity": "⤓"})
        self.assertEqual(data["glyphs"], {
            "scope": dict(zip("ILPUG?", "🟦🟩🟨🟧🟥❓")),
            "amount": dict(zip("1FNBS?", "📄📑📚📦🌊❓")),
            "complexity": dict(zip("TEMHN?", "⚪⬜🔶🔺💥❓")),
        })

    def test_stats_table_sits_above_the_details(self):
        dialog = re.search(r"<dialog.*?</dialog>", self.page, re.S).group(0)
        cells = re.findall(r'<div class="stat" data-stat="(\w+)">', dialog)
        self.assertEqual(cells, ["kind", "status", "group", "scope", "amount", "complexity"])
        self.assertLess(dialog.index('class="stats"'), dialog.index("<dl>"))
        for gone in ['data-field="kind"', 'data-field="scope"']:
            with self.subTest(gone):
                self.assertNotIn(f"<dd {gone}", dialog, "moved into the stats table")

    def test_stylesheet_colours_each_cell_from_the_tokens(self):
        for rule in [".stat.status-done", ".stat.scope-L", ".stat.scope-unknown",
                     ".stat.complexity-H", ".stat.kind-release"]:
            with self.subTest(rule):
                self.assertRegex(self.page, re.escape(rule) + r"\s*\{[^}]*var\(--wv-")

    def test_cells_are_written_as_text_only(self):
        self.assertNotRegex(self.page, r"innerHTML|outerHTML|insertAdjacentHTML")
