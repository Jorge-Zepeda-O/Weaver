"""End-to-end oracle for merge event M1: the real CLI on the real example plan."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "weaver_plan.toml"
NODE_IDS = ["A0", "A1", "A2", "A3", "A4", "A5", "M1", "V1", "A6"]


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
        self.assertIn("9 nodes, 13 edges", self.result.stdout)

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
    Rebuilt only at merge nodes, never on a lane branch: the lanes would conflict on it, so
    on a lane these tests may be red until the lane merges.
    """
    DOCS = ROOT / "docs" / "example"

    def test_markdown_is_current(self):
        from weaver import load_plan
        from weaver.markdown import to_markdown
        self.assertEqual((self.DOCS / "PLAN.md").read_text(encoding="utf-8"),
                         to_markdown(load_plan(EXAMPLE)),
                         "docs/example/ is stale: rebuild it (see the docstring)")

    def test_svg_and_html_are_current(self):
        """T-9: the README's image and the page go stale as easily as the Markdown. Graphviz
        is byte-stable between runs, but another Graphviz version may draw differently."""
        from weaver import load_plan
        from weaver.dot import render_svg
        from weaver.html import build_html
        plan = load_plan(EXAMPLE)
        svg = render_svg(plan)
        for name, expected in [("plan.svg", svg), ("PLAN.html", build_html(plan, svg))]:
            with self.subTest(name):
                self.assertEqual((self.DOCS / name).read_text(encoding="utf-8"), expected,
                                 f"docs/example/{name} is stale: rebuild it (see the docstring), "
                                 "or your Graphviz version draws differently")

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

    DIMS = 'scope = "L"\namount = "1"\ncomplexity = "E"\n'

    def _build(self, nodes: str, *flags: str, dims: bool = True) -> subprocess.CompletedProcess:
        """Every node is assessed unless ``dims`` is off, so A4-3 stays out of these tests."""
        if dims:
            nodes = nodes.replace("[[node]]\n", "[[node]]\n" + TestOverlapReporting.DIMS)
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


class TestUnassessedReporting(unittest.TestCase):
    """A4-3: an unassessed node is loud on stderr, counted in the summary, and fails --strict."""
    HEADER = TestOverlapReporting.HEADER
    _build = TestOverlapReporting._build
    BARE = '[[node]]\nid = "a"\ntitle = "a"\n'

    def test_unassessed_node_warns_and_is_counted(self):
        result = self._build(self.BARE, dims=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(), ["weaver: unassessed: a — no scope, amount, complexity"])
        self.assertTrue(result.stdout.endswith(", 1 unassessed\n"), result.stdout)

    def test_strict_fails_on_an_unassessed_node(self):
        self.assertEqual(self._build(self.BARE, "--strict", dims=False).returncode, 3)

    def test_assessed_plan_says_nothing(self):
        result = self._build(self.BARE, "--strict")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertNotIn("unassessed", result.stdout)


class TestReleaseReporting(unittest.TestCase):
    """A4-4: an orphan release fails --strict; an unordered pair of releases is only a note."""
    HEADER = '[plan]\nschema = 3\ntitle = "x"\n'
    _build = TestOverlapReporting._build

    @staticmethod
    def _release(node_id: str, *deps: str) -> str:
        return (f'[[node]]\nid = "{node_id}"\ntitle = "{node_id}"\nkind = "release"\n'
                f'verify = "v"\ndeps = {list(deps)!r}\n').replace("'", '"')

    def test_orphan_release_warns_and_fails_strict(self):
        plan = self._release("r1") + self._release("r2") + self._release("r3")
        result = self._build(plan, "--strict")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stderr.splitlines(),
                         ["weaver: orphan release: r2 — depends on no release; the first release is r1",
                          "weaver: orphan release: r3 — depends on no release; the first release is r1"])
        self.assertTrue(result.stdout.endswith(", 2 orphan releases\n"), result.stdout)

    def test_unordered_releases_are_a_note_that_passes_strict(self):
        plan = self._release("r1") + self._release("r2", "r1") + self._release("r3", "r1")
        result = self._build(plan, "--strict")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         ["weaver: unordered releases: r3 — neither r2 nor r3 depends on the other"])
        self.assertTrue(result.stdout.endswith(", 1 unordered release pair\n"), result.stdout)


class TestDoneOnUnfinishedReporting(unittest.TestCase):
    """A4-4: a done node on unfinished build work fails --strict; at runtime it is a note."""
    HEADER = TestOverlapReporting.HEADER
    _build = TestOverlapReporting._build
    E = '[[node]]\nid = "e"\ntitle = "e"\n'

    def test_build_seam_warns_and_fails_strict(self):
        result = self._build(self.E + '[[node]]\nid = "r"\ntitle = "r"\nstatus = "done"\n'
                             'deps = ["e"]\n', "--strict")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stderr.splitlines(),
                         ["weaver: done on unfinished: r — depends on e, which is todo"])
        self.assertTrue(result.stdout.endswith(", 1 done node on unfinished work\n"), result.stdout)

    def test_runtime_seam_is_a_note_that_passes_strict(self):
        result = self._build(self.E + '[[node]]\nid = "r"\ntitle = "r"\nstatus = "done"\n'
                             'runtime_deps = ["e"]\n', "--strict")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         ["weaver: done on unfinished: r — depends at runtime on e, which is todo"])


class TestStaleReporting(unittest.TestCase):
    """A4-2: a stale [[overlap]] entry is loud and fails --strict; history is only counted."""
    HEADER = TestOverlapReporting.HEADER
    _build = TestOverlapReporting._build
    ORDERED = ('[[node]]\nid = "a"\ntitle = "a"\ngroup = "g"\nfiles = ["f.py"]\n'
               '[[node]]\nid = "b"\ntitle = "b"\ngroup = "h"\nfiles = ["f.py"]\ndeps = ["a"]\n')
    LANDED = ('[[node]]\nid = "a"\ntitle = "a"\ngroup = "g"\nfiles = ["f.py"]\nstatus = "done"\n'
              '[[node]]\nid = "b"\ntitle = "b"\ngroup = "h"\nfiles = ["f.py"]\nstatus = "done"\n'
              '[[node]]\nid = "m"\ntitle = "m"\nkind = "merge"\nstatus = "done"\n'
              'verify = "v"\ndeps = ["a", "b"]\n')
    ACK = TestAcknowledgedReporting.ACK
    WHY = "shares a lane or a dependency with every other node named"

    def test_stale_entry_is_listed_per_node_and_counted_per_entry(self):
        result = self._build(self.ORDERED + self.ACK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         [f"weaver: stale acknowledgement: f.py — a {self.WHY}",
                          f"weaver: stale acknowledgement: f.py — b {self.WHY}"])
        self.assertTrue(result.stdout.endswith(", 1 stale acknowledgement\n"), result.stdout)

    def test_strict_fails_on_a_stale_entry_even_with_no_overlap(self):
        self.assertEqual(self._build(self.ORDERED + self.ACK, "--strict").returncode, 3)

    def test_history_is_counted_not_listed_and_passes_strict(self):
        result = self._build(self.LANDED + self.ACK, "--strict")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith(", 1 acknowledgement now history (prunable)\n"),
                        result.stdout)

class TestSnapshotAndHistory(unittest.TestCase):
    """A4-5: weaver snapshot writes a stamped folder; weaver history reads a series of them."""
    PLAN = '[plan]\nschema = 3\ntitle = "x"\n[[node]]\nid = "a"\ntitle = "a"\nstatus = "{}"\n'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_reports_the_folder_it_wrote(self):
        plan = self.root / "p.toml"
        plan.write_text(self.PLAN.format("todo"), encoding="utf-8")
        result = _run("snapshot", str(plan), "-d", str(self.root / "snaps"))
        self.assertEqual(result.returncode, 0, result.stderr)
        (folder,) = (self.root / "snaps").iterdir()
        self.assertEqual(result.stdout, f"weaver: snapshot → {folder}\n")
        self.assertTrue((folder / "plan.toml").is_file())

    def test_snapshot_of_a_missing_plan_exits_2(self):
        result = _run("snapshot", str(self.root / "nope.toml"), "-d", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such plan file", result.stderr)

    def test_snapshot_of_an_invalid_plan_exits_1(self):
        plan = self.root / "p.toml"
        plan.write_text("not toml [", encoding="utf-8")
        self.assertEqual(_run("snapshot", str(plan), "-d", str(self.root / "s")).returncode, 1)
        self.assertFalse((self.root / "s").exists())

    def _snap(self, name: str, status: str | None) -> None:
        (self.root / name).mkdir()
        if status:
            (self.root / name / "plan.toml").write_text(self.PLAN.format(status), encoding="utf-8")

    def test_history_lists_early_work_and_counts_what_it_read(self):
        self._snap("PLAN_20261119_000001", None)
        self._snap("PLAN_20261119_000002", "doing")
        result = _run("history", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "weaver: skipped PLAN_20261119_000001: no plan.toml\n")
        self.assertEqual(result.stdout.splitlines(),
                         ["weaver: a first seen doing in PLAN_20261119_000002",
                          "weaver: 1 snapshot read, 1 skipped; "
                          "1 node built or started before it was planned"])

    def test_history_says_so_when_everything_was_planned_first(self):
        self._snap("PLAN_20261119_000001", "todo")
        self._snap("PLAN_20261119_000002", "done")
        self.assertEqual(_run("history", str(self.root)).stdout,
                         "weaver: 2 snapshots read; every node was planned before work started\n")

    def test_history_that_read_nothing_is_loud(self):
        """'I read nothing' must never look like 'I found nothing'."""
        self._snap("PLAN_20261119_000001", None)
        result = _run("history", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertIn(f"weaver: no readable snapshot in {self.root}", result.stderr)

    def test_history_of_a_missing_folder_exits_2(self):
        self.assertEqual(_run("history", str(self.root / "nope")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
