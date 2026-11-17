"""End-to-end oracle for merge event M1: the real CLI on the real example plan."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "weaver_plan.toml"
NODE_IDS = ["A0", "A1", "A2", "A3", "A4", "A5", "M1"]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "weaver", *args],
                          cwd=ROOT, capture_output=True, text=True)


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "out"
        cls.result = _run("build", str(EXAMPLE), "-o", str(cls.out))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exits_zero_and_reports_what_it_built(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        # A1:1 + A2:1 + A3:2 + A4:1 + A5:2 (one runtime) + M1:4 = 11
        self.assertIn("7 nodes, 11 edges", self.result.stdout)

    def test_svg_has_every_node(self):
        svg = (self.out / "plan.svg").read_text(encoding="utf-8")
        for node_id in NODE_IDS:
            with self.subTest(node_id):
                self.assertIn(f'id="node-{node_id}"', svg)

    def test_html_embeds_the_graph_and_the_data(self):
        page = (self.out / "PLAN.html").read_text(encoding="utf-8")
        self.assertIn("<svg", page)
        self.assertIn('id="plan-data"', page)
        for node_id in NODE_IDS:
            with self.subTest(node_id):
                self.assertIn(f'id="node-{node_id}"', page)

    def test_markdown_has_a_row_per_node(self):
        md = (self.out / "PLAN.md").read_text(encoding="utf-8")
        rows = [line for line in md.splitlines() if line.startswith("| ")][1:]
        self.assertEqual(len(rows), len(NODE_IDS))

    def test_pdf_is_written(self):
        self.assertEqual((self.out / "PLAN.pdf").read_bytes()[:5], b"%PDF-")


class TestFailures(unittest.TestCase):
    def test_invalid_plan_exits_1_and_names_the_defect(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.toml"
            bad.write_text('[plan]\nschema = 1\ntitle = "x"\n[[node]]\nid = "a"\ntitle = "y"\ndeps = ["zz"]\n',
                           encoding="utf-8")
            result = _run("build", str(bad), "-o", str(Path(tmp) / "out"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown dependency 'zz'", result.stderr)

    def test_missing_plan_file_exits_2(self):
        result = _run("build", "does-not-exist.toml", "-o", "unused")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such plan file", result.stderr)

    def test_missing_command_exits_2(self):
        self.assertEqual(_run().returncode, 2)


if __name__ == "__main__":
    unittest.main()
