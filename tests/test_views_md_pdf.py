import subprocess
import tempfile
import unittest
from pathlib import Path

from weaver import parse_plan
from weaver.markdown import to_markdown
from weaver.pdf import build_pdf

PLAN = parse_plan({
    "plan": {"schema": 1, "title": "Tiny plan", "caption": "Two atoms and a merge.",
             "goal": "Both sides joined."},
    "node": [
        {"id": "a", "title": "Left | side", "notes": "first line\nsecond line", "group": "left",
         "scope": "L", "complexity": "M", "verify": "tests/test_a.py"},
        {"id": "b", "title": "Right side", "status": "done", "amount": "?"},
        {"id": "m", "title": "Join", "kind": "merge", "deps": ["a"], "runtime_deps": ["b"],
         "decisions": ["D-3", "other:D-22"]},
    ],
})

# Stands in for dot.render_svg's output: the marker proves the graph is drawn, not just linked.
FIXTURE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50">'
               '<text x="10" y="30">SVGMARKER</text></svg>')


class TestMarkdown(unittest.TestCase):
    def setUp(self):
        self.md = to_markdown(PLAN)
        self.rows = [line for line in self.md.splitlines() if line.startswith("| ")][1:]

    def test_one_row_per_node(self):
        self.assertEqual([row.split(" | ")[0] for row in self.rows], ["| a", "| b", "| m"])

    def test_every_row_has_eight_cells(self):
        for row in self.rows:
            with self.subTest(row):
                # Escaped pipes (\|) don't count as cell borders.
                self.assertEqual(row.replace("\\|", "").count("|"), 9)

    def test_seam_type_is_shown(self):
        self.assertIn("| a, b (runtime) |", self.rows[2])

    def test_no_dependencies_shows_a_dash(self):
        self.assertTrue(self.rows[0].endswith("| — |"))

    def test_notes_keep_their_line_breaks(self):
        self.assertIn("### a: Left | side\n\nfirst line\nsecond line", self.md)

    def test_nodes_without_notes_get_no_heading(self):
        self.assertNotIn("### b:", self.md)


class TestMarkdownV1(unittest.TestCase):
    def setUp(self):
        self.md = to_markdown(PLAN)
        self.rows = [line for line in self.md.splitlines() if line.startswith("| ")][1:]

    def test_goal_follows_the_title(self):
        self.assertIn("# Tiny plan\n\n**Goal:** Both sides joined.\n", self.md)

    def test_row_cells(self):
        cells = [c.strip() for c in self.rows[0].strip("|").split(" | ")]
        self.assertEqual(cells[3:7], ["left", "todo", "S:L A:- C:M", "tests/test_a.py"])

    def test_unguarded_merge_says_so(self):
        self.assertIn("| — (unguarded) |", self.rows[2])

    def test_decisions_alone_earn_a_field_note(self):
        self.assertIn("### m: Join\n\nDecisions: D-3, other:D-22\n", self.md)

    def test_key_explains_the_codes(self):
        for text in ["S = scope", "I independent", "A = amount", "S stream", "C = complexity",
                     "N novel", "- unassessed", "? unknowable"]:
            with self.subTest(text):
                self.assertIn(text, self.md)


class TestPdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "plan.pdf"
        build_pdf(PLAN, FIXTURE_SVG, cls.path)
        cls.text = subprocess.run(["pdftotext", "-layout", str(cls.path), "-"],
                                  capture_output=True, text=True, check=True).stdout

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_is_a_pdf(self):
        self.assertEqual(self.path.read_bytes()[:5], b"%PDF-")

    def test_graph_is_drawn(self):
        self.assertIn("SVGMARKER", self.text)

    def test_caption_and_every_node_appear(self):
        for expected in ["Two atoms and a merge.", "a: Left | side", "b: Right side", "m: Join"]:
            with self.subTest(expected):
                self.assertIn(expected, self.text)

    def test_v1_fields_appear(self):
        for expected in ["Goal: Both sides joined.", "left", "S:L A:- C:M", "verify: tests/test_a.py",
                         "decisions: D-3, other:D-22", "unguarded", "S = scope"]:
            with self.subTest(expected):
                self.assertIn(expected, self.text)

    def test_notes_and_seams_appear(self):
        for expected in ["first line", "second line", "depends on a, b (runtime)"]:
            with self.subTest(expected):
                self.assertIn(expected, self.text)


if __name__ == "__main__":
    unittest.main()
