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
    return parse_plan({"plan": {"title": "T", **header}, "node": list(nodes)})


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
            (a5["id"], a5["title"], a5["kind"], a5["status"], a5["owner"], a5["notes"], a5["deps"]),
            (node.id, node.title, node.kind, node.status, node.owner, node.notes,
             [{"id": "A0", "seam": "build"}, {"id": "A2", "seam": "runtime"}]))

    def test_dependents_are_computed_from_edges_with_their_seam(self):
        nodes = _data(self.page)["nodes"]
        cases = [
            ("A2", [{"id": "A3", "seam": "build"}, {"id": "A5", "seam": "runtime"}]),
            ("A0", [{"id": i, "seam": "build"} for i in ("A1", "A2", "A3", "A5")]),
            ("M1", []),
        ]
        for node_id, expected in cases:
            with self.subTest(node_id):
                self.assertEqual(nodes[node_id]["dependents"], expected)

    def test_title_and_caption_are_shown(self):
        self.assertIn("<h1>weaver — practice run</h1>", self.page)
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
                 "prefers-color-scheme: dark", "g.node { cursor: pointer; }", 'setAttribute("viewBox"']
        for needle in cases:
            with self.subTest(needle):
                self.assertIn(needle, self.page)


class TestEscaping(unittest.TestCase):
    def test_notes_cannot_break_out_of_the_data_block(self):
        page = build_html(_plan({"id": "a", "title": "x", "notes": BREAKOUT}), "<svg></svg>")
        self.assertNotIn("</script><b>", page)
        self.assertEqual(_data(page)["nodes"]["a"]["notes"], BREAKOUT)

    def test_data_block_has_no_raw_less_than(self):
        page = build_html(_plan({"id": "a", "title": "<x>", "owner": "<!--", "notes": "<"}), "<svg></svg>")
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
