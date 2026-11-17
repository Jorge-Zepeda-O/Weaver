import subprocess
import tempfile
import unittest
from pathlib import Path

from weaver import parse_plan
from weaver.markdown import to_markdown
from weaver.pdf import build_pdf

PLAN = parse_plan({
    "plan": {"title": "Tiny plan", "caption": "Two atoms and a merge."},
    "node": [
        {"id": "a", "title": "Left | side", "notes": "first line\nsecond line"},
        {"id": "b", "title": "Right side", "status": "done"},
        {"id": "m", "title": "Join", "kind": "merge", "deps": ["a"], "runtime_deps": ["b"]},
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

    def test_every_row_has_six_cells(self):
        for row in self.rows:
            with self.subTest(row):
                # Escaped pipes (\|) don't count as cell borders.
                self.assertEqual(row.replace("\\|", "").count("|"), 7)

    def test_seam_type_is_shown(self):
        self.assertIn("| a, b (runtime) |", self.rows[2])

    def test_no_dependencies_shows_a_dash(self):
        self.assertTrue(self.rows[0].endswith("| — |"))

    def test_notes_keep_their_line_breaks(self):
        self.assertIn("### a: Left | side\n\nfirst line\nsecond line", self.md)

    def test_nodes_without_notes_get_no_heading(self):
        self.assertNotIn("### b:", self.md)


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

    def test_notes_and_seams_appear(self):
        for expected in ["first line", "second line", "depends on a, b (runtime)"]:
            with self.subTest(expected):
                self.assertIn(expected, self.text)


if __name__ == "__main__":
    unittest.main()
