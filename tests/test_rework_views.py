"""A3-11: a rework shows as a dotted edge from the fixed node to its fix, which leaves the
layout alone, and in both nodes' panels ("Reworks", "Reworked by")."""
import unittest
import xml.etree.ElementTree as ET

from weaver import parse_plan
from weaver.dot import render_svg, to_dot
from weaver.html import build_html, plan_data

SVG_NS = "{http://www.w3.org/2000/svg}"
PLAN = parse_plan({
    "plan": {"schema": 3, "title": "T"},
    "node": [{"id": "b4", "title": "cards", "status": "done"},
             {"id": "b5", "title": "panel", "status": "done"},
             {"id": "a36", "title": "scope colours the text", "deps": ["b5"], "reworks": ["b4", "b5"]}]})


class TestGraph(unittest.TestCase):
    def test_edge_from_each_fixed_node_to_its_fix_outside_the_layout(self):
        dot = to_dot(PLAN)
        for target in ("b4", "b5"):
            with self.subTest(target):
                self.assertIn(f'"{target}" -> "a36" [class="rework", style=dotted, color="#0d9488", '
                              'arrowhead=empty, constraint=false];', dot)

    def test_rework_edge_is_its_own_class_beside_the_dependency(self):
        svg = ET.fromstring(render_svg(PLAN))
        classes = sorted(g.get("class") for g in svg.iter(f"{SVG_NS}g") if "edge" in (g.get("class") or ""))
        self.assertEqual(classes, ["edge rework", "edge rework", "edge seam-build"])

    def test_no_reworks_no_rework_edges(self):
        plan = parse_plan({"plan": {"schema": 3, "title": "T"}, "node": [{"id": "a", "title": "x"}]})
        self.assertNotIn("rework", to_dot(plan))


class TestPanel(unittest.TestCase):
    def test_both_sides_name_each_other(self):
        nodes = plan_data(PLAN)["nodes"]
        self.assertEqual(nodes["a36"]["reworks"], [{"id": "b4"}, {"id": "b5"}])
        self.assertEqual(nodes["b4"]["reworked_by"], [{"id": "a36"}])
        self.assertEqual((nodes["a36"]["reworked_by"], nodes["b4"]["reworks"]), ([], []))

    def test_page_has_the_rows_and_the_key(self):
        page = build_html(PLAN, render_svg(PLAN))
        for needle in ['<dt>Reworks</dt><dd><ul data-field="reworks"></ul></dd>',
                       '<dt>Reworked by</dt><dd><ul data-field="reworked_by"></ul></dd>',
                       'fillList("reworked_by", node.reworked_by);',
                       "rework (from the fixed node to its fix)"]:
            with self.subTest(needle):
                self.assertIn(needle, page)
