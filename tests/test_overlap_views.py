"""A3-4: an overlap shows in every view. A ⚠ on both nodes' cards, the panel's list (file,
other node, any reason), and a list in the key area of the Markdown and the PDF."""
import re
import unittest
import xml.etree.ElementTree as ET

from weaver import parse_plan
from weaver.dot import render_svg, to_dot
from weaver.html import _STYLE, build_html, plan_data
from weaver.markdown import to_markdown
from weaver.model import overlaps
from weaver.pdf import _page

SVG_NS = "{http://www.w3.org/2000/svg}"

# f.py: a (g) × b (h), open. x.py: a (g) × c (i), acknowledged. q touches nothing shared.
PLAN = parse_plan({
    "plan": {"schema": 3, "title": "T"},
    "node": [{"id": "a", "title": "a", "group": "g", "files": ["f.py", "x.py"]},
             {"id": "b", "title": "Bee", "group": "h", "files": ["f.py"]},
             {"id": "c", "title": "c", "group": "i", "files": ["x.py"]},
             {"id": "q", "title": "q", "group": "j", "files": ["y.py"]}],
    "overlap": [{"file": "x.py", "nodes": ["a", "c"], "reason": "c only reads it"}]})
LINES = ["f.py — a (g) × b (h)", "x.py — a (g) × c (i) — acknowledged: c only reads it"]
QUIET = parse_plan({"plan": {"schema": 3, "title": "T"},
                    "node": [{"id": "a", "title": "a", "files": ["f.py"]}]})


def _statement(node_id: str) -> str:
    (line,) = [ln for ln in to_dot(PLAN).splitlines() if ln.strip().startswith(f'"{node_id}" [')]
    return line


class TestDescribe(unittest.TestCase):
    def test_one_line_per_overlap_shared_by_every_view(self):
        self.assertEqual([o.describe(PLAN) for o in overlaps(PLAN)], LINES)


class TestCard(unittest.TestCase):
    def test_both_nodes_of_an_overlap_carry_the_mark(self):
        """Acknowledged or not: an acknowledgement explains an overlap, it never hides it."""
        for node_id, marked in [("a", True), ("b", True), ("c", True), ("q", False)]:
            with self.subTest(node_id):
                header = re.search(r"<TD[^>]*>(<B>.*?)</TD>", _statement(node_id)).group(1)
                self.assertEqual(header.endswith(' · <FONT COLOR="#d97706">⚠</FONT>'), marked, header)
                self.assertEqual(" overlap" in re.search(r'class="([^"]*)"', _statement(node_id)).group(1),
                                 marked)

    def test_mark_survives_into_the_svg(self):
        svg = ET.fromstring(render_svg(PLAN))
        group = next(g for g in svg.iter(f"{SVG_NS}g") if g.get("id") == "node-a")
        header = "".join(next(group.iter(f"{SVG_NS}text")).itertext())
        self.assertEqual(header, "a · ○ todo · ⚠")
        self.assertIn("overlap", group.get("class").split())

    def test_mark_is_amber_in_the_svg_and_on_the_page(self):
        """The mark gets one clear alert colour; the scope colour of the
        rest of the text must not repaint it (a tspan's own class beats the text's rule)."""
        svg = ET.fromstring(render_svg(PLAN))
        group = next(g for g in svg.iter(f"{SVG_NS}g") if g.get("id") == "node-a")
        mark = next(t for t in group.iter(f"{SVG_NS}tspan") if t.text == "⚠")
        self.assertEqual((mark.get("class"), mark.get("fill")), ("alert", "#d97706"))
        self.assertIn("#viewport g.node text tspan.alert { fill: var(--wv-alert); }", _STYLE)


class TestPanel(unittest.TestCase):
    def test_each_node_lists_its_overlaps_with_the_other_node_and_any_reason(self):
        nodes = plan_data(PLAN)["nodes"]
        cases = [("a", [{"file": "f.py", "other": "b", "reason": ""},
                        {"file": "x.py", "other": "c", "reason": "c only reads it"}]),
                 ("b", [{"file": "f.py", "other": "a", "reason": ""}]),
                 ("c", [{"file": "x.py", "other": "a", "reason": "c only reads it"}]),
                 ("q", [])]
        for node_id, expected in cases:
            with self.subTest(node_id):
                self.assertEqual(nodes[node_id]["overlaps"], expected)

    def test_page_has_the_list_the_legend_row_and_the_wiring(self):
        page = build_html(PLAN, render_svg(PLAN))
        for needle in ['<ul data-field="overlaps">', "fillOverlaps(", "acknowledged: ",
                       "<dt>Overlap (⚠)</dt>"]:
            with self.subTest(needle):
                self.assertIn(needle, page)

    def test_reason_reaches_the_page_only_as_data(self):
        """The reason is the plan's text: it travels in the escaped JSON block, never as markup."""
        hostile = parse_plan({
            "plan": {"schema": 3, "title": "T"},
            "node": [{"id": "a", "title": "a", "group": "g", "files": ["f.py"]},
                     {"id": "b", "title": "b", "group": "h", "files": ["f.py"]}],
            "overlap": [{"file": "f.py", "nodes": ["a", "b"], "reason": "</script><b>x</b>"}]})
        page = build_html(hostile, render_svg(hostile))
        self.assertNotIn("<b>x</b>", page)


class TestKeyArea(unittest.TestCase):
    def test_markdown_lists_every_overlap_after_the_key(self):
        md = to_markdown(PLAN)
        block = md[md.index("**Overlaps:**"):]
        self.assertGreater(md.index("**Overlaps:**"), md.index("**Key:**"))
        self.assertEqual([ln[2:] for ln in block.splitlines() if ln.startswith("- ")][:2], LINES)

    def test_pdf_lists_every_overlap_in_the_key_area(self):
        page = _page(PLAN, "<svg/>")
        self.assertIn("<p class='key overlaps'>Overlaps:<br>" + "<br>".join(LINES) + "</p>", page)

    def test_no_overlaps_means_no_list(self):
        self.assertNotIn("Overlaps", to_markdown(QUIET))
        self.assertNotIn("Overlaps", _page(QUIET, "<svg/>"))


if __name__ == "__main__":
    unittest.main()
