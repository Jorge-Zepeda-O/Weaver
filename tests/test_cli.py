"""End-to-end oracle for merge event M1: the real CLI on the real example plan."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "weaver_plan.toml"
NODE_IDS = ["A0", "A1", "A2", "A3", "A4", "A5", "M1", "V1"]


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
        # A1:1 + A2:1 + A3:2 + A4:1 + A5:2 (one runtime) + M1:4 + V1:1 = 12
        self.assertIn("8 nodes, 12 edges", self.result.stdout)

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


class TestCommittedExample(unittest.TestCase):
    """docs/example/ is what the README shows; it must match the example plan.

    Regenerate with: python -m weaver build examples/weaver_plan.toml -o docs/example/
    """
    DOCS = ROOT / "docs" / "example"

    def test_markdown_is_current(self):
        from weaver import load_plan
        from weaver.markdown import to_markdown
        self.assertEqual((self.DOCS / "PLAN.md").read_text(encoding="utf-8"),
                         to_markdown(load_plan(EXAMPLE)),
                         "docs/example/ is stale: rebuild it (see the docstring)")

    def test_every_view_is_committed(self):
        for name in ["plan.svg", "PLAN.html", "PLAN.md", "PLAN.pdf"]:
            with self.subTest(name):
                self.assertTrue((self.DOCS / name).is_file())

    def test_svg_shows_every_node(self):
        svg = (self.DOCS / "plan.svg").read_text(encoding="utf-8")
        for node_id in NODE_IDS:
            with self.subTest(node_id):
                self.assertIn(f'id="node-{node_id}"', svg)


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


class TestOverlapReporting(unittest.TestCase):
    """A3-2: overlaps are loud on stderr but only fail the build under --strict."""
    HEADER = '[plan]\nschema = 3\ntitle = "x"\n'
    LINE = "weaver: overlap: f.py — a (g) × b (no group)"

    def _build(self, nodes: str, *flags: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p.toml"
            plan.write_text(self.HEADER + nodes, encoding="utf-8")
            return _run("build", str(plan), "-o", str(Path(tmp) / "out"), *flags)

    CLEAN = ('[[node]]\nid = "a"\ntitle = "a"\ngroup = "g"\nfiles = ["f.py"]\n'
             '[[node]]\nid = "b"\ntitle = "b"\nfiles = ["f.py"]\ndeps = ["a"]\n')
    CLASH = ('[[node]]\nid = "a"\ntitle = "a"\ngroup = "g"\nfiles = ["f.py"]\n'
             '[[node]]\nid = "b"\ntitle = "b"\nfiles = ["f.py"]\n')

    def test_no_overlap_is_silent(self):
        result = self._build(self.CLEAN)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("overlap", result.stderr)
        self.assertTrue(result.stdout.startswith("weaver: 2 nodes, 1 edges → "), result.stdout)
        self.assertNotIn("overlap", result.stdout)

    def test_overlap_warns_on_stderr_and_still_exits_zero(self):
        result = self._build(self.CLASH)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(), [self.LINE])
        self.assertTrue(result.stdout.endswith(", 1 overlap\n"), result.stdout)

    def test_summary_pluralises(self):
        three = self.CLASH + '[[node]]\nid = "c"\ntitle = "c"\ngroup = "i"\nfiles = ["f.py"]\n'
        self.assertTrue(self._build(three).stdout.endswith(", 3 overlaps\n"))

    def test_strict_with_overlap_exits_3_but_still_builds(self):
        result = self._build(self.CLASH, "--strict")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stderr.splitlines(), [self.LINE])
        self.assertIn(", 1 overlap\n", result.stdout)

    def test_strict_without_overlap_exits_zero(self):
        self.assertEqual(self._build(self.CLEAN, "--strict").returncode, 0)



class TestAcknowledgedReporting(unittest.TestCase):
    """A3-3: an acknowledged overlap stays on stderr with its reason; --strict passes it."""
    HEADER = TestOverlapReporting.HEADER
    _build = TestOverlapReporting._build
    ACK = '[[overlap]]\nfile = "f.py"\nnodes = ["a", "b"]\nreason = "different hunks"\n'
    THIRD = '[[node]]\nid = "c"\ntitle = "c"\ngroup = "i"\nfiles = ["f.py"]\n'

    def test_acknowledged_overlap_is_still_listed_with_its_reason(self):
        result = self._build(TestOverlapReporting.CLASH + self.ACK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         [TestOverlapReporting.LINE + " — acknowledged: different hunks"])
        self.assertTrue(result.stdout.endswith(", 1 overlap (1 acknowledged)\n"), result.stdout)

    def test_strict_passes_when_every_overlap_is_acknowledged(self):
        self.assertEqual(self._build(TestOverlapReporting.CLASH + self.ACK, "--strict").returncode, 0)

    def test_strict_fails_on_any_unacknowledged_overlap(self):
        result = self._build(TestOverlapReporting.CLASH + self.THIRD + self.ACK, "--strict")
        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stdout.endswith(", 3 overlaps (1 acknowledged)\n"), result.stdout)


if __name__ == "__main__":
    unittest.main()
