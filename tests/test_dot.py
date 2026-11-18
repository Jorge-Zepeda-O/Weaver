import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from weaver import load_plan, parse_plan
from weaver.dot import RELEASE_COLOUR, RULE_COLOUR, TITLE_WIDTH, render_svg, to_dot

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "weaver_plan.toml"
SVG_NS = "{http://www.w3.org/2000/svg}"


def _plan(*nodes: dict):
    return parse_plan({"plan": {"schema": 1, "title": "T"}, "node": list(nodes)})


def _statement(dot: str, node_id: str) -> str:
    (line,) = [ln for ln in dot.splitlines() if ln.strip().startswith(f'"{node_id}" [')]
    return line


def _label(statement: str) -> str:
    """The HTML-like label's markup, between ``label=<`` and its closing ``>``."""
    return re.search(r"label=<(.*?)>, shape=", statement).group(1)


def _cells(statement: str) -> list[str]:
    """Each table cell's content, in order: header, title, then marker and letter per code."""
    return re.findall(r"<TD[^>]*>(.*?)</TD>", _label(statement))


def _node_group(svg: str, node_id: str) -> ET.Element:
    return next(g for g in ET.fromstring(svg).iter(f"{SVG_NS}g") if g.get("id") == f"node-{node_id}")


def _node_text(svg: str, node_id: str) -> list[str]:
    """The lines drawn inside one node, in document order, with their runs joined."""
    return ["".join(t.itertext()) for t in _node_group(svg, node_id).iter(f"{SVG_NS}text")]


def _shape_centre_x(group: ET.Element) -> float:
    """The middle of the node's first shape, from its points or path coordinates."""
    shape = next(e for e in group if e.tag in (f"{SVG_NS}polygon", f"{SVG_NS}path"))
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", shape.get("points") or shape.get("d"))]
    xs = numbers[0::2]
    return (min(xs) + max(xs)) / 2


def _card_rules(group: ET.Element) -> tuple[tuple[float, float, float], float | None]:
    """The header rule's left end, right end and height, and the divider's x (None when the
    card has no codes), read from the polygons classed as rules."""
    rule = divider = None
    for polygon in group.iter(f"{SVG_NS}polygon"):
        if polygon.get("class") != "rule":
            continue
        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", polygon.get("points"))]
        xs, ys = numbers[0::2], numbers[1::2]
        if len(set(ys)) == 1:
            rule = (min(xs), max(xs), ys[0])
        else:
            divider = xs[0]
    assert rule is not None, "no header rule found"
    return rule, divider


def _layout_plan():
    """Every card shape, with and without codes: atom, merge, release."""
    return parse_plan({"plan": {"schema": 2, "title": "T"}, "node": [
        {"id": "a", "title": "A title long enough to wrap onto two lines", "scope": "L",
         "complexity": "M"},
        {"id": "m", "title": "y", "kind": "merge", "verify": "v", "deps": ["a"], "amount": "1"},
        {"id": "r", "title": "z", "kind": "release", "verify": "v", "deps": ["m"], "scope": "G"},
        {"id": "q", "title": "A plain card with no codes at all", "deps": ["a"]}]})


def _classes(element: ET.Element) -> set[str]:
    return set(element.get("class", "").split())


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

    def test_release_is_an_octagon_with_bold_purple_text(self):
        """D-15: shape, colour and weight mark a release; purple is in no scope colour."""
        plan = parse_plan({"plan": {"schema": 2, "title": "T"}, "node": [
            {"id": "r", "title": "v1", "kind": "release", "verify": "tag", "scope": "P",
             "complexity": "E"}]})
        statement = _statement(to_dot(plan), "r")
        self.assertIn("shape=octagon, style=filled", statement)
        self.assertIn(f'fontcolor="{RELEASE_COLOUR}"', statement)
        self.assertEqual(statement.count("fontcolor="), 1, "the release colour wins over scope's")
        self.assertNotIn("<FONT", statement, "no run of a release's text takes the scope colour")
        self.assertIn('fontname="Helvetica-Bold"', statement)
        self.assertIn(' color="#64748b"', statement, "complexity still owns the border")
        self.assertEqual(_cells(statement)[2:], ["↕", "P", "↔", "-", "⤓", "E"],
                         "scope stays readable in the code")

    def test_fill_follows_status(self):
        cases = [("todo", "#ffffff"), ("doing", "#bfdbfe"), ("done", "#d1fae5"), ("blocked", "#fca5a5")]
        for status, colour in cases:
            with self.subTest(status):
                dot = to_dot(_plan({"id": "a", "title": "x", "status": status}))
                self.assertIn(f'fillcolor="{colour}"', _statement(dot, "a"))

    def test_line_style_follows_seam(self):
        dot = to_dot(_plan({"id": "a", "title": "x"}, {"id": "b", "title": "y"},
                           {"id": "c", "title": "z", "deps": ["a"], "runtime_deps": ["b"]}))
        lines = [ln.strip() for ln in dot.splitlines()]
        self.assertIn('"a" -> "c" [class="seam-build"];', lines, "build seam must be a plain solid edge")
        self.assertIn('"b" -> "c" [class="seam-runtime", style=dashed];', lines)

    def test_label_is_a_card_of_header_over_a_rule_then_title(self):
        """B4, A3-7: an HTML-like table, header row (bold id, status), a rule, the title row."""
        dot = to_dot(_plan({"id": "a", "title": "Do it"}))
        self.assertIn(f'label=<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" COLOR="{RULE_COLOUR}">'
                      "<TR><TD><B>a</B> · ○ todo</TD></TR><HR/><TR><TD>Do it</TD></TR></TABLE>>",
                      _statement(dot, "a"))

    def test_codes_sit_in_a_right_column_behind_a_divider(self):
        """A3-7 layout C: the header spans the card; the title fills the left across the code
        rows; a divider; then marker and letter in separate cells, so the letters line up."""
        dot = to_dot(_plan({"id": "a", "title": "x", "scope": "L", "complexity": "M"}))
        self.assertIn('<TR><TD COLSPAN="3"><B>a</B> · ○ todo</TD></TR><HR/>'
                      '<TR><TD ROWSPAN="3">x</TD><VR/><TD>↕</TD><TD ALIGN="LEFT">L</TD></TR>'
                      '<TR><TD>↔</TD><TD ALIGN="LEFT">-</TD></TR>'
                      '<TR><TD>⤓</TD><TD ALIGN="LEFT">M</TD></TR></TABLE>', _label(_statement(dot, "a")))

    def test_status_is_printed_so_the_fill_is_never_alone(self):
        """B3: status was the one thing shown by colour alone."""
        for status, mark in [("todo", "○"), ("doing", "◐"), ("done", "✓"), ("blocked", "✕")]:
            with self.subTest(status):
                dot = to_dot(_plan({"id": "a", "title": "x", "status": status}))
                self.assertEqual(_cells(_statement(dot, "a"))[0], f"<B>a</B> · {mark} {status}")

    def test_label_escapes_markup_in_the_title(self):
        """Every character the label language treats as markup becomes an entity."""
        cases = [('say "hi"', "say &quot;hi&quot;"), ("a & b", "a &amp; b"),
                 ("<b>x</b>", "&lt;b&gt;x&lt;/b&gt;"), ("&amp;", "&amp;amp;"),
                 ("\\N", "\\\\N"), ("a\\\\b", "a\\\\\\\\b")]
        for title, cell in cases:
            with self.subTest(title):
                self.assertEqual(_cells(_statement(to_dot(_plan({"id": "a", "title": title})), "a"))[1],
                                 cell)

    def test_long_title_wraps_at_word_boundaries(self):
        title = "Details panel: a stats table on top, icons and colours throughout"
        lines = _cells(_statement(to_dot(_plan({"id": "a", "title": title})), "a"))[1].split("<BR/>")
        self.assertGreater(len(lines), 1, "the title was not wrapped")
        self.assertTrue(all(len(ln) <= TITLE_WIDTH for ln in lines), lines)
        self.assertEqual(" ".join(lines), title, "wrapping lost or changed words")

    def test_a_word_longer_than_the_width_is_kept_whole(self):
        word = "x" * (TITLE_WIDTH + 5)
        self.assertEqual(_cells(_statement(to_dot(_plan({"id": "a", "title": word})), "a"))[1], word)


class TestFindDot(unittest.TestCase):
    def test_dot_is_looked_up_on_the_path(self):
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="<svg/>", stderr="")
        with mock.patch("weaver.dot.shutil.which", return_value="/opt/gv/bin/dot"), \
             mock.patch("weaver.dot.subprocess.run", return_value=ok) as run:
            render_svg(_plan({"id": "a", "title": "A"}))
        self.assertEqual(run.call_args.args[0][0], "/opt/gv/bin/dot")

    def test_missing_graphviz_says_so(self):
        with mock.patch("weaver.dot.shutil.which", return_value=None), \
             mock.patch("weaver.dot.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "Graphviz"):
                render_svg(_plan({"id": "a", "title": "A"}))
        run.assert_not_called()


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

    def test_scope_sets_the_text_colour(self):
        """D-18: scope is reach, shown in the text; the darker shades keep it readable."""
        cases = [("I", "#1d4ed8"), ("L", "#15803d"), ("P", "#a16207"), ("U", "#c2410c"),
                 ("G", "#b91c1c"), ("?", "#7f1d1d")]
        for code, colour in cases:
            with self.subTest(code):
                statement = _statement(to_dot(_plan({"id": "a", "title": "x", "scope": code})), "a")
                self.assertIn(f'fontcolor="{colour}"', statement, "scope colours the whole text")
                self.assertEqual(_cells(statement)[2:], ["↕", code, "↔", "-", "⤓", "-"])
                self.assertNotIn(' color="', statement, "scope no longer colours the border")

    def test_complexity_sets_the_border_colour(self):
        """D-18: the border is the node's weight: calm grey to red, like the complexity glyphs."""
        cases = [("T", "#94a3b8"), ("E", "#64748b"), ("M", "#ea580c"), ("H", "#dc2626"),
                 ("N", "#7f1d1d"), ("?", "#7f1d1d")]
        for code, colour in cases:
            with self.subTest(code):
                dot = to_dot(_plan({"id": "a", "title": "x", "complexity": code}))
                self.assertIn(f' color="{colour}"', _statement(dot, "a"))

    def test_complexity_sets_the_border_weight(self):
        cases = [("T", "1"), ("E", "1.5"), ("M", "2.5"), ("H", "3.5"), ("N", "5"), ("?", "5")]
        for code, width in cases:
            with self.subTest(code):
                dot = to_dot(_plan({"id": "a", "title": "x", "complexity": code}))
                self.assertIn(f"penwidth={width}", _statement(dot, "a"))

    def test_amount_sets_the_number_of_outlines(self):
        """D-16: uncapped on purpose; '?' ranks worst, as many outlines as stream."""
        cases = [("1", "1"), ("F", "2"), ("N", "3"), ("B", "4"), ("S", "5"), ("?", "5")]
        for code, count in cases:
            with self.subTest(code):
                dot = to_dot(_plan({"id": "a", "title": "x", "amount": code}))
                self.assertIn(f"peripheries={count}", _statement(dot, "a"))

    def test_outlines_apply_to_every_kind(self):
        plan = parse_plan({"plan": {"schema": 2, "title": "T"}, "node": [
            {"id": k, "title": k, "kind": k, "verify": "v", "amount": "N"}
            for k in ("atom", "merge", "release")]})
        dot = to_dot(plan)
        for kind in ("atom", "merge", "release"):
            with self.subTest(kind):
                self.assertIn("peripheries=3", _statement(dot, kind))

    def test_unassessed_dimensions_leave_the_border_alone(self):
        statement = _statement(to_dot(_plan({"id": "a", "title": "x"})), "a")
        self.assertNotIn("color=", statement.replace("fillcolor=", ""))
        self.assertNotIn("penwidth", statement)
        self.assertNotIn("peripheries", statement)

    def test_label_prints_the_codes_so_colour_is_never_alone(self):
        dot = to_dot(_plan({"id": "a", "title": "x", "scope": "L", "complexity": "M"}))
        self.assertEqual(_cells(_statement(dot, "a")),
                         ["<B>a</B> · ○ todo", "x", "↕", "L", "↔", "-", "⤓", "M"])

    def test_code_row_without_a_scope_is_all_ink(self):
        dot = to_dot(_plan({"id": "a", "title": "x", "complexity": "M"}))
        self.assertEqual(_cells(_statement(dot, "a"))[2:], ["↕", "-", "↔", "-", "⤓", "M"])

    def test_no_code_column_when_nothing_is_assessed(self):
        statement = _statement(to_dot(_plan({"id": "a", "title": "x"})), "a")
        self.assertEqual(len(_cells(statement)), 2)
        self.assertNotIn("<VR/>", statement)

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
                for g in root.iter(f"{SVG_NS}g") if "node" in _classes(g)}

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
        ids = {g.get("id") for g in groups if "node" in _classes(g)}
        self.assertEqual(ids, {f"node-{n.id}" for n in self.plan.nodes})

    def test_prolog_and_doctype_are_removed(self):
        self.assertTrue(self.svg.lstrip().startswith("<!--") or self.svg.lstrip().startswith("<svg"))
        self.assertNotIn("<?xml", self.svg)
        self.assertNotIn("<!DOCTYPE", self.svg)

    def test_runtime_edge_renders_dashed(self):
        match = re.search(r'<g id="edge\d+" class="edge[^"]*">\s*<title>A2&#45;&gt;A5</title>\s*<path [^>]*>',
                          self.svg)
        self.assertIsNotNone(match, "edge A2->A5 not found")
        self.assertIn("stroke-dasharray", match.group(0))

    def test_label_text_is_escaped_in_svg(self):
        svg = render_svg(_plan({"id": "a", "title": 'say "hi" & <b>'}))
        self.assertNotIn("<b>", svg)
        ET.fromstring(svg)  # still well-formed XML

    def test_hostile_titles_render_as_their_literal_text(self):
        """B4: markup, entities and DOT escapes in a title are drawn, never interpreted."""
        for title in ["<b>bold</b>", "a & b", "&amp;", "say \"hi\"", "back\\slash \\N \\G", "a\\\\b", "]>"]:
            with self.subTest(title):
                texts = _node_text(render_svg(_plan({"id": "a", "title": title})), "a")
                self.assertIn(title, texts)

    def test_scope_colours_every_line(self):
        """D-18: the whole text takes the scope colour."""
        svg = render_svg(_plan({"id": "a", "title": "x", "scope": "L", "amount": "F", "complexity": "M"}))
        fills = [t.get("fill") for t in _node_group(svg, "a").iter(f"{SVG_NS}text")]
        self.assertEqual(fills, ["#15803d"] * 8)  # header, title, three markers, three letters

    def test_every_line_is_centred_on_the_card_rules(self):
        """A3-6, A3-7: one middle-anchored <text> per line, so no device's font can shift it
        (Graphviz anchors each run at its start, with its own font's widths). The centres are
        measured from the rules: the header on the header rule, the title between the rule's
        left end and the divider, a marker between the divider and its letter. The letters
        keep one shared start, so they line up."""
        svg = render_svg(_layout_plan())
        for node_id in ("a", "m", "r", "q"):
            group = _node_group(svg, node_id)
            (left, right, rule_y), divider = _card_rules(group)
            header, *rest = group.iter(f"{SVG_NS}text")
            title = [t for t in rest if divider is None or float(t.get("x")) < divider]
            codes = [t for t in rest if t not in title]
            expected = [(header, (left + right) / 2)]
            expected += [(t, (left + divider) / 2 if divider else (left + right) / 2) for t in title]
            rows: dict[str, list[ET.Element]] = {}
            for text in codes:
                rows.setdefault(text.get("y"), []).append(text)
            letters = [max(row, key=lambda t: float(t.get("x"))) for row in rows.values()]
            for marker, letter in zip([min(row, key=lambda t: float(t.get("x"))) for row in rows.values()],
                                      letters):
                expected.append((marker, (divider + float(letter.get("x"))) / 2))
            for text, centre in expected:
                with self.subTest(node=node_id, line="".join(text.itertext())):
                    self.assertEqual(text.get("text-anchor"), "middle")
                    self.assertAlmostEqual(float(text.get("x")), centre, places=1)
            self.assertLess(float(header.get("y")), rule_y, "the header sits above its rule")
            self.assertTrue(all(float(t.get("y")) > rule_y for t in rest), "body below the rule")
            if divider is None:
                self.assertAlmostEqual((left + right) / 2, _shape_centre_x(group), places=1)
            else:
                self.assertEqual(len(rows), 3, "one row per dimension")
                self.assertEqual({t.get("text-anchor") for t in letters}, {"start"})
                self.assertEqual(len({t.get("x") for t in letters}), 1, "the letters line up")

    def test_rules_are_classed_and_quiet(self):
        """A3-7: the rules carry class "rule" and the rule colour, so the page's status fill,
        border and hover styles pass them by; the shape itself is never classed a rule."""
        group = _node_group(render_svg(_layout_plan()), "a")
        polygons = [e for e in group if e.tag in (f"{SVG_NS}polygon", f"{SVG_NS}path")]
        rules = [p for p in polygons if p.get("class") == "rule"]
        self.assertEqual(len(rules), 2, "the header rule and the divider")
        self.assertEqual({(r.get("fill"), r.get("stroke")) for r in rules}, {(RULE_COLOUR, RULE_COLOUR)})
        self.assertIsNone(polygons[0].get("class"), "the node's shape is not a rule")

    def test_header_keeps_the_bold_id_inside_its_line(self):
        svg = render_svg(_plan({"id": "a", "title": "x"}))
        header = next(_node_group(svg, "a").iter(f"{SVG_NS}text"))
        spans = [(s.text, s.get("font-weight")) for s in header.iter(f"{SVG_NS}tspan")]
        self.assertEqual(spans, [("a", "bold"), (" · ○ todo", None)])

    def test_dot_failure_raises_with_stderr(self):
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="syntax error")
        with mock.patch("weaver.dot.subprocess.run", return_value=failed):
            with self.assertRaises(RuntimeError) as ctx:
                render_svg(self.plan)
        self.assertIn("syntax error", str(ctx.exception))


class TestSvgClasses(unittest.TestCase):
    """B1/D-13: every node, edge and lane carries classes the page's stylesheet can target."""

    @classmethod
    def setUpClass(cls):
        plan = parse_plan({"plan": {"schema": 2, "title": "T"}, "node": [
            {"id": "a-1", "title": "A", "status": "done", "group": "side-lane",
             "scope": "L", "amount": "1", "complexity": "?"},
            {"id": "m", "title": "M", "kind": "merge", "deps": ["a-1"]},
            {"id": "r", "title": "R", "kind": "release", "verify": "tag", "runtime_deps": ["m"]}]})
        cls.svg = render_svg(plan)
        cls.groups = list(ET.fromstring(cls.svg).iter(f"{SVG_NS}g"))

    def _node(self, node_id: str) -> set[str]:
        (group,) = [g for g in self.groups if g.get("id") == f"node-{node_id}"]
        return _classes(group)

    def test_node_classes_name_kind_status_and_dimensions(self):
        self.assertEqual(self._node("a-1"),
                         {"node", "kind-atom", "status-done", "scope-L", "amount-1",
                          "complexity-unknown"})

    def test_unassessed_dimensions_add_no_class(self):
        self.assertEqual(self._node("m"), {"node", "kind-merge", "status-todo", "unguarded"})

    def test_release_classes(self):
        self.assertEqual(self._node("r"), {"node", "kind-release", "status-todo"})

    def test_edges_carry_their_seam(self):
        seams = {g.find(f"{SVG_NS}title").text: _classes(g) - {"edge"}
                 for g in self.groups if "edge" in _classes(g)}
        self.assertEqual(seams, {"a-1->m": {"seam-build"}, "m->r": {"seam-runtime"}})

    def test_lanes_are_marked(self):
        lanes = [g for g in self.groups if "cluster" in _classes(g)]
        self.assertEqual([_classes(g) for g in lanes], [{"cluster", "lane"}])

    def test_no_class_keeps_graphviz_dash_entity(self):
        self.assertNotRegex(self.svg, r'class="[^"]*&#45;')


if __name__ == "__main__":
    unittest.main()
