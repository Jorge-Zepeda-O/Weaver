import base64
import hashlib
import json
import re
import unittest
from pathlib import Path

from weaver import load_plan, parse_plan
from weaver.dot import render_svg
from weaver.html import build_html

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "weaver_plan.toml"
BREAKOUT = "</script><b>x</b>"


def _plan(*nodes: dict, **header: str):
    return parse_plan({"plan": {"schema": 1, "title": "T", **header}, "node": list(nodes)})


def _data(page: str) -> dict:
    match = re.search(r'<script type="application/json" id="plan-data">(.*?)</script>', page, re.S)
    assert match, "plan-data block not found"
    return json.loads(match.group(1))


class TestExamplePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_plan(EXAMPLE)
        cls.page = build_html(cls.plan, render_svg(cls.plan))

    def test_every_node_id_is_in_the_embedded_data(self):
        self.assertEqual(set(_data(self.page)["nodes"]), {n.id for n in self.plan.nodes})

    def test_every_node_group_is_inlined(self):
        for node in self.plan.nodes:
            with self.subTest(node.id):
                self.assertIn(f'id="node-{node.id}"', self.page)

    def test_node_record_carries_every_modal_field(self):
        a5 = _data(self.page)["nodes"]["A5"]
        node = self.plan.node("A5")
        self.assertEqual(
            (a5["id"], a5["title"], a5["kind"], a5["status"], a5["group"], a5["notes"],
             a5["scope"], a5["amount"], a5["complexity"], a5["verify"], a5["decisions"],
             a5["unguarded"], a5["deps"]),
            (node.id, node.title, node.kind, node.status, node.group, node.notes,
             node.scope, node.amount, node.complexity, node.verify, list(node.decisions), False,
             [{"id": "A0", "seam": "build"}, {"id": "A2", "seam": "runtime"}]))

    def test_dependents_are_computed_from_edges_with_their_seam(self):
        nodes = _data(self.page)["nodes"]
        cases = [
            ("A2", [{"id": "A3", "seam": "build"}, {"id": "A5", "seam": "runtime"}]),
            ("A0", [{"id": i, "seam": "build"} for i in ("A1", "A2", "A3", "A5")]),
            ("M1", [{"id": "V1", "seam": "build"}]),
            ("V1", []),
        ]
        for node_id, expected in cases:
            with self.subTest(node_id):
                self.assertEqual(nodes[node_id]["dependents"], expected)

    def test_title_and_caption_are_shown(self):
        self.assertIn("<h1>weaver — the plan that built it</h1>", self.page)
        self.assertIn('<p class="caption">One plan file, three views.', self.page)

    def test_no_external_resources(self):
        for needle in ("http://", "https://", "src=", "href=", "url(", "@import"):
            with self.subTest(needle):
                self.assertNotIn(needle, self.page)

    def test_no_innerhtml_or_eval(self):
        # The example plan's own notes mention innerHTML, so the data block is excluded.
        code = re.sub(r'(?s)<script type="application/json".*?</script>', "", self.page)
        for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write"):
            with self.subTest(needle):
                self.assertNotIn(needle, code)

    def test_svg_is_inline_without_prolog(self):
        self.assertNotIn("<?xml", self.page)
        self.assertNotIn("<!DOCTYPE svg", self.page)
        self.assertRegex(self.page, r'(?s)<div id="viewport">\s*(<!--.*?-->\s*)*<svg ')

    def test_csp_hashes_match_the_inline_script_and_style(self):
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', self.page).group(1)
        self.assertIn("default-src 'none'", csp)
        cases = [("script-src", r"<script>(.*?)</script>"), ("style-src", r"<style>(.*?)</style>")]
        for directive, pattern in cases:
            with self.subTest(directive):
                (body,) = re.findall(pattern, self.page, re.S)
                digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                self.assertIn(f"{directive} 'sha256-{digest}'", csp)

    def test_viewer_contract_is_present(self):
        cases = ['id="reset-view"', 'id="node-dialog"', 'class="close"', "white-space: pre-wrap",
                 "prefers-color-scheme: dark", "g.node { cursor: pointer; }", 'setAttribute("viewBox"',
                 # A3-5: the find box, the hash wiring and the highlight style.
                 'id="find"', 'id="find-status"', 'role="status"', '"hashchange"', "makeFinder(",
                 "g.node.found"]
        for needle in cases:
            with self.subTest(needle):
                self.assertIn(needle, self.page)


class TestSchemaV1Page(unittest.TestCase):
    def test_goal_is_shown_and_escaped(self):
        page = build_html(_plan({"id": "a", "title": "x"}, goal="a < b"), "<svg></svg>")
        self.assertIn('<p class="goal"><strong>Goal:</strong> a &lt; b</p>', page)

    def test_no_goal_means_no_goal_paragraph(self):
        self.assertNotIn('class="goal"', build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>"))

    def test_modal_has_a_slot_for_every_v1_field(self):
        page = build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>")
        # B5 moved group and the dimensions into the stats table (data-stat).
        slots = [("stat", "group"), ("stat", "scope"), ("stat", "amount"), ("stat", "complexity"),
                 ("field", "verify"), ("field", "decisions")]
        for kind, name in slots:
            with self.subTest(name):
                self.assertIn(f'data-{kind}="{name}"', page)

    def test_payload_carries_the_term_names(self):
        terms = _data(build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>"))["terms"]
        self.assertEqual(terms["scope"]["L"], "local")
        self.assertEqual(terms["amount"]["S"], "stream")
        self.assertEqual(terms["complexity"]["N"], "novel")
        self.assertEqual({k: set(v) for k, v in terms.items()},
                         {"scope": set("ILPUG?"), "amount": set("1FNBS?"), "complexity": set("TEMHN?")})

    def test_legend_names_every_code(self):
        page = build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>")
        legend = re.search(r'<details id="legend">(.*?)</details>', page, re.S).group(1)
        for code in ["I independent", "G global", "? unknowable", "T trivial", "N novel",
                     "1 one", "S stream", "unguarded merge", "release", "runtime seam",
                     "○ todo", "◐ doing", "✓ done", "✕ blocked"]:
            with self.subTest(code):
                self.assertIn(code, re.sub(r"<[^>]+>", " ", legend).replace("  ", " "))

    def test_legend_draws_amount_as_outlines(self):
        page = build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>")
        legend = re.search(r'<details id="legend">(.*?)</details>', page, re.S).group(1)
        row = re.search(r"<dt>Amount \(outlines\)</dt><dd>(.*?)</dd>", legend).group(1)
        counts = [len(re.findall(r"<rect ", svg)) for svg in re.findall(r"<svg.*?</svg>", row)]
        self.assertEqual(counts, [1, 2, 3, 4, 5, 5])

    def test_panel_shows_status_as_symbol_and_word(self):
        page = build_html(_plan({"id": "a", "title": "x", "status": "done"}), "<svg></svg>")
        self.assertEqual(_data(page)["nodes"]["a"]["status_label"], "✓ done")
        # B5: the stats cell for status shows the label (behaviour checked in test_panel).
        self.assertIn('text: node.status_label', page)

    def test_no_inline_style_attributes(self):
        # The CSP admits the one <style> block by hash; a style="" attribute would be refused.
        page = build_html(_plan({"id": "a", "title": "x", "scope": "G"}), "<svg></svg>")
        self.assertNotRegex(page, r"\sstyle=")


class TestEscaping(unittest.TestCase):
    def test_notes_cannot_break_out_of_the_data_block(self):
        page = build_html(_plan({"id": "a", "title": "x", "notes": BREAKOUT}), "<svg></svg>")
        self.assertNotIn("</script><b>", page)
        self.assertEqual(_data(page)["nodes"]["a"]["notes"], BREAKOUT)

    def test_data_block_has_no_raw_less_than(self):
        page = build_html(_plan({"id": "a", "title": "<x>", "group": "<!--", "notes": "<"}), "<svg></svg>")
        match = re.search(r'id="plan-data">(.*?)</script>', page, re.S)
        self.assertNotIn("<", match.group(1))

    def test_markup_text_is_html_escaped(self):
        cases = [
            ("h1", dict(title="a < b & c"), "<h1>a &lt; b &amp; c</h1>"),
            ("head title", dict(title="a < b & c"), "<title>a &lt; b &amp; c</title>"),
            ("caption", dict(caption="<i>&"), '<p class="caption">&lt;i&gt;&amp;</p>'),
        ]
        for name, header, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, build_html(_plan({"id": "a", "title": "x"}, **header), "<svg></svg>"))

    def test_no_caption_means_no_caption_paragraph(self):
        self.assertNotIn('class="caption"', build_html(_plan({"id": "a", "title": "x"}), "<svg></svg>"))


if __name__ == "__main__":
    unittest.main()
