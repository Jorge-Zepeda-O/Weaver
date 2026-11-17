import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from weaver import load_plan, parse_plan
from weaver.dot import render_svg, to_dot

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "weaver_plan.toml"
SVG_NS = "{http://www.w3.org/2000/svg}"


def _plan(*nodes: dict):
    return parse_plan({"plan": {"title": "T"}, "node": list(nodes)})


def _statement(dot: str, node_id: str) -> str:
    (line,) = [ln for ln in dot.splitlines() if ln.strip().startswith(f'"{node_id}" [')]
    return line


class TestToDot(unittest.TestCase):
    def test_layout_is_left_to_right(self):
        self.assertIn("rankdir=LR;", to_dot(_plan({"id": "a", "title": "x"})))

    def test_every_node_carries_the_contract_id(self):
        plan = load_plan(EXAMPLE)
        dot = to_dot(plan)
        for node in plan.nodes:
            with self.subTest(node.id):
                self.assertIn(f'id="node-{node.id}"', _statement(dot, node.id))

    def test_shape_follows_kind(self):
        dot = to_dot(_plan({"id": "a", "title": "x"}, {"id": "m", "title": "y", "kind": "merge"}))
        cases = [("a", 'shape=box, style="rounded,filled"'), ("m", "shape=hexagon, style=filled")]
        for node_id, expected in cases:
            with self.subTest(node_id):
                self.assertIn(expected, _statement(dot, node_id))

    def test_fill_follows_status(self):
        cases = [("todo", "#ffffff"), ("doing", "#dbeafe"), ("done", "#dcfce7"), ("blocked", "#fee2e2")]
        for status, colour in cases:
            with self.subTest(status):
                dot = to_dot(_plan({"id": "a", "title": "x", "status": status}))
                self.assertIn(f'fillcolor="{colour}"', _statement(dot, "a"))

    def test_line_style_follows_seam(self):
        dot = to_dot(_plan({"id": "a", "title": "x"}, {"id": "b", "title": "y"},
                           {"id": "c", "title": "z", "deps": ["a"], "runtime_deps": ["b"]}))
        lines = [ln.strip() for ln in dot.splitlines()]
        self.assertIn('"a" -> "c";', lines, "build seam must be a plain solid edge")
        self.assertIn('"b" -> "c" [style=dashed];', lines)

    def test_label_is_id_then_title(self):
        dot = to_dot(_plan({"id": "a", "title": "Do it"}))
        self.assertIn('label="a\\nDo it"', _statement(dot, "a"))

    def test_label_escapes_backslash_and_quote(self):
        dot = to_dot(_plan({"id": "a", "title": 'say "hi" \\N'}))
        self.assertIn('label="a\\nsay \\"hi\\" \\\\N"', _statement(dot, "a"))


class TestRenderSvg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_plan(EXAMPLE)
        cls.svg = render_svg(cls.plan)

    def test_example_svg_has_a_group_per_node_id(self):
        for node in self.plan.nodes:
            with self.subTest(node.id):
                self.assertIn(f'id="node-{node.id}"', self.svg)

    def test_contract_id_survives_xml_parsing(self):
        groups = ET.fromstring(self.svg).iter(f"{SVG_NS}g")
        ids = {g.get("id") for g in groups if g.get("class") == "node"}
        self.assertEqual(ids, {f"node-{n.id}" for n in self.plan.nodes})

    def test_prolog_and_doctype_are_removed(self):
        self.assertTrue(self.svg.lstrip().startswith("<!--") or self.svg.lstrip().startswith("<svg"))
        self.assertNotIn("<?xml", self.svg)
        self.assertNotIn("<!DOCTYPE", self.svg)

    def test_runtime_edge_renders_dashed(self):
        match = re.search(r'<g id="edge\d+" class="edge">\s*<title>A2&#45;&gt;A5</title>\s*<path [^>]*>',
                          self.svg)
        self.assertIsNotNone(match, "edge A2->A5 not found")
        self.assertIn("stroke-dasharray", match.group(0))

    def test_label_text_is_escaped_in_svg(self):
        svg = render_svg(_plan({"id": "a", "title": 'say "hi" & <b>'}))
        self.assertNotIn("<b>", svg)
        ET.fromstring(svg)  # still well-formed XML

    def test_dot_failure_raises_with_stderr(self):
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="syntax error")
        with mock.patch("weaver.dot.subprocess.run", return_value=failed):
            with self.assertRaises(RuntimeError) as ctx:
                render_svg(self.plan)
        self.assertIn("syntax error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
