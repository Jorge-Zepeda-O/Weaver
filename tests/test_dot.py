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
    return parse_plan({"plan": {"schema": 1, "title": "T"}, "node": list(nodes)})


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
        dot = to_dot(_plan({"id": "a", "title": "x"}, {"id": "m", "title": "y", "kind": "merge",
                                                         "verify": "tests/test_m.py"}))
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


def _cluster_bodies(dot: str) -> dict[str, list[str]]:
    """Cluster label -> the node ids declared inside that cluster."""
    clusters, current = {}, None
    for line in (ln.strip() for ln in dot.splitlines()):
        if line.startswith("subgraph "):
            current = []
        elif current is not None and line.startswith("label="):
            clusters[line.removeprefix("label=").rstrip(";")] = current
        elif current is not None and line == "}":
            current = None
        elif current is not None and line.startswith('"'):
            current.append(line.split('"')[1])
    return clusters


class TestSchemaV1Dot(unittest.TestCase):
    def test_unguarded_merge_has_a_dashed_border(self):
        dot = to_dot(_plan({"id": "m", "title": "y", "kind": "merge"}))
        self.assertIn('shape=hexagon, style="filled,dashed"', _statement(dot, "m"))

    def test_scope_sets_the_border_colour(self):
        cases = [("I", "#2563eb"), ("L", "#0891b2"), ("P", "#ca8a04"), ("U", "#ea580c"),
                 ("G", "#dc2626"), ("?", "#7f1d1d")]
        for code, colour in cases:
            with self.subTest(code):
                dot = to_dot(_plan({"id": "a", "title": "x", "scope": code}))
                self.assertIn(f'color="{colour}"', _statement(dot, "a"))

    def test_complexity_sets_the_border_weight(self):
        cases = [("T", "1"), ("E", "1.5"), ("M", "2.5"), ("H", "3.5"), ("N", "5"), ("?", "5")]
        for code, width in cases:
            with self.subTest(code):
                dot = to_dot(_plan({"id": "a", "title": "x", "complexity": code}))
                self.assertIn(f"penwidth={width}", _statement(dot, "a"))

    def test_unassessed_dimensions_leave_the_border_alone(self):
        statement = _statement(to_dot(_plan({"id": "a", "title": "x"})), "a")
        self.assertNotIn("color=", statement.replace("fillcolor=", ""))
        self.assertNotIn("penwidth", statement)

    def test_label_prints_the_codes_so_colour_is_never_alone(self):
        dot = to_dot(_plan({"id": "a", "title": "x", "scope": "L", "complexity": "M"}))
        self.assertIn('label="a\\nx\\nS:L A:- C:M"', _statement(dot, "a"))

    def test_groups_become_lanes(self):
        dot = to_dot(_plan({"id": "a", "title": "x", "group": "sub-1"},
                           {"id": "b", "title": "y", "group": "main"},
                           {"id": "c", "title": "z", "group": "sub-1"},
                           {"id": "d", "title": "w"}))
        self.assertEqual(_cluster_bodies(dot), {'"sub-1"': ["a", "c"], '"main"': ["b"]})
        self.assertEqual(dot.count('"d" ['), 1, "an ungrouped node is still declared once")

    def test_group_label_is_escaped(self):
        dot = to_dot(_plan({"id": "a", "title": "x", "group": 'say "hi"'}))
        self.assertIn('label="say \\"hi\\"";', dot)


class TestLayoutReadsLeftToRight(unittest.TestCase):
    """Every edge points rightwards, even when a lane spans the whole history.

    Graphviz ranks each cluster on its own unless told otherwise, so a lane that
    holds both the first node and the last merge pulls them together.
    """

    @staticmethod
    def _node_x(svg: str) -> dict[str, float]:
        root = ET.fromstring(svg)
        return {g.get("id").removeprefix("node-"): float(g.find(f"{SVG_NS}text").get("x"))
                for g in root.iter(f"{SVG_NS}g") if g.get("class") == "node"}

    def test_no_edge_points_backwards(self):
        def node(i, group, deps=(), kind="atom"):
            return {"id": i, "title": i, "group": group, "deps": list(deps), "kind": kind}
        plan = _plan(node("a", "main"), node("b", "side", ["a"]), node("c", "side", ["b"]),
                     node("d", "side", ["c"]), node("m", "main", ["d"], "merge"))
        x = self._node_x(render_svg(plan))
        backwards = [(e.source, e.target) for e in plan.edges() if x[e.target] <= x[e.source]]
        self.assertEqual(backwards, [])


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
