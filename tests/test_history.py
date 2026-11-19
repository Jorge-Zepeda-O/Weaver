"""A4-5: snapshots of a plan, and what their history shows was built before it was planned."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HEADER = '[plan]\nschema = 3\ntitle = "T"\n'
NOW = datetime(2026, 11, 19, 21, 5, 9)


def _plan(*nodes: tuple[str, str]) -> str:
    return HEADER + "".join(f'[[node]]\nid = "{i}"\ntitle = "{i}"\nstatus = "{s}"\n'
                            for i, s in nodes)


class TestSnapshot(unittest.TestCase):
    """weaver snapshot (ruled 20261119): PLAN_<YYYYMMDD_HHMMSS>/ with plan.toml + HTML + MD."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = self.root / "p.toml"
        self.plan.write_text(_plan(("a", "todo")), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _snapshot(self, now=NOW):
        from weaver.history import snapshot
        return snapshot(self.plan, self.root / "snaps", now)

    def test_folder_is_named_by_the_time(self):
        self.assertEqual(self._snapshot().name, "PLAN_20261119_210509")

    def test_holds_the_plan_byte_for_byte_and_the_views(self):
        folder = self._snapshot()
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["PLAN.html", "PLAN.md", "plan.toml"])
        self.assertEqual((folder / "plan.toml").read_bytes(), self.plan.read_bytes())

    def test_never_overwrites_a_snapshot(self):
        self._snapshot()
        with self.assertRaises(FileExistsError):
            self._snapshot()

    def test_an_invalid_plan_writes_nothing(self):
        from weaver import PlanError
        self.plan.write_text(HEADER + '[[node]]\nid = "a"\ntitle = "a"\ndeps = ["zz"]\n',
                             encoding="utf-8")
        with self.assertRaises(PlanError):
            self._snapshot()
        self.assertFalse((self.root / "snaps").exists())


class TestHistory(unittest.TestCase):
    """weaver history (ruled 20261119): a node whose first appearance is done or doing was
    built or started before it was planned. The first snapshot is no baseline: work in it has
    no plan on record either, so it is listed like the rest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _snap(self, name: str, text: str | None) -> None:
        folder = self.root / name
        folder.mkdir()
        if text is not None:
            (folder / "plan.toml").write_text(text, encoding="utf-8")

    def _history(self):
        from weaver.history import history
        return history(self.root)

    def test_truth_table(self):
        cases = [
            ("planned, then built", [("todo",), ("done",)], []),
            ("first seen done", [("done",)], [("x", "done", "PLAN_20261119_000001")]),
            ("first seen doing", [("doing",), ("done",)], [("x", "doing", "PLAN_20261119_000001")]),
            ("first seen blocked is planned", [("blocked",)], []),
            ("appears in a later snapshot already done", [None, ("done",)],
             [("x", "done", "PLAN_20261119_000002")]),
        ]
        for case, (name, states, expected) in enumerate(cases):
            with self.subTest(name):
                self.root = Path(self.tmp.name) / f"case{case}"
                self.root.mkdir()
                for n, state in enumerate(states, start=1):
                    nodes = [("x", state[0])] if state else []
                    self._snap(f"PLAN_20261119_00000{n}", _plan(("keep", "todo"), *nodes))
                report = self._history()
                self.assertEqual([(e.node, e.status, e.snapshot) for e in report.early], expected)

    def test_reads_in_time_order_not_creation_order(self):
        self._snap("PLAN_20261119_000002", _plan(("x", "done")))
        self._snap("PLAN_20261119_000001", _plan(("x", "todo")))
        self.assertEqual(self._history().early, ())

    def test_counts_what_it_read_and_skips_folders_without_a_plan(self):
        self._snap("PLAN_20261119_000001", None)
        self._snap("PLAN_20261119_000002", _plan(("x", "todo")))
        report = self._history()
        self.assertEqual(report.read, ("PLAN_20261119_000002",))
        self.assertEqual(report.skipped, (("PLAN_20261119_000001", "no plan.toml"),))

    def test_an_invalid_snapshot_is_skipped_with_its_reason(self):
        self._snap("PLAN_20261119_000001", "not toml [")
        self._snap("PLAN_20261119_000002", _plan(("x", "todo")))
        self.assertEqual([s[0] for s in self._history().skipped], ["PLAN_20261119_000001"])

    def test_ignores_anything_not_named_like_a_snapshot(self):
        self._snap("notes", _plan(("x", "done")))
        (self.root / "PLAN_20261118_160018.html").write_text("old render", encoding="utf-8")
        self._snap("PLAN_20261119_000001", _plan(("x", "todo")))
        report = self._history()
        self.assertEqual((report.read, report.skipped, report.early),
                         (("PLAN_20261119_000001",), (), ()))


if __name__ == "__main__":
    unittest.main()
