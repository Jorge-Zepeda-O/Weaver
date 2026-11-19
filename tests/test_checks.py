"""A4-3, A4-4: plan checks beyond overlaps, each a truth table over the ruled cases."""
import unittest

from weaver import parse_plan

DIMS = {"scope": "L", "amount": "1", "complexity": "E"}


def _node(node_id: str, status: str = "todo", **fields) -> dict:
    return {"id": node_id, "title": node_id, "status": status, **DIMS, **fields}


def _findings(*nodes: dict) -> list[tuple[str, str, str, bool]]:
    from weaver.checks import findings
    plan = parse_plan({"plan": {"schema": 3, "title": "T"}, "node": list(nodes)})
    return [(f.check, f.node, f.detail, f.strict) for f in findings(plan)]


class TestUnassessed(unittest.TestCase):
    """A4-3 (ruled 20261119): every node, whatever its status, carries all three dimensions;
    '?' is an assessment (unknowable), only an absent value is unassessed. Fails --strict."""

    def test_truth_table(self):
        cases = [
            ("all three", _node("a"), []),
            ("'?' counts as assessed", _node("a", scope="?", amount="?", complexity="?"), []),
            ("one missing", {**_node("a"), "scope": None},
             [("unassessed", "a", "no scope", True)]),
            ("all missing", {"id": "a", "title": "a"},
             [("unassessed", "a", "no scope, amount, complexity", True)]),
            ("done nodes too", {**_node("a", "done"), "complexity": None},
             [("unassessed", "a", "no complexity", True)]),
            ("doing nodes too", {**_node("a", "doing"), "amount": None},
             [("unassessed", "a", "no amount", True)]),
        ]
        for name, node, expected in cases:
            with self.subTest(name):
                node = {k: v for k, v in node.items() if v is not None}
                self.assertEqual(_findings(node), expected)

    def test_in_plan_order(self):
        result = _findings({"id": "b", "title": "b"}, _node("c"), {"id": "a", "title": "a"})
        self.assertEqual([f[1] for f in result], ["b", "a"])


def _release(node_id: str, deps=(), status: str = "todo", **fields) -> dict:
    return _node(node_id, status, kind="release", verify="v", deps=list(deps), **fields)


class TestReleaseOrder(unittest.TestCase):
    """A4-4 (ruled 20261119, tiered): every release but the first depends on some release
    (an orphan fails --strict); two releases neither depending on the other get a note that
    never fails --strict, so a hotfix beside a newer release is legitimate. Of the releases
    with no release upstream, the first in the file is the first (A5-1's tie-break)."""

    def _release_findings(self, *nodes):
        return [f for f in _findings(*nodes) if f[0] != "unassessed"]

    def test_truth_table(self):
        orphan = ("orphan release", "r2", "depends on no release; the first release is r1", True)
        cases = [
            ("one release", [_release("r1")], []),
            ("a chain", [_release("r1"), _release("r2", deps=["r1"])], []),
            ("a chain through an atom", [_release("r1"), _node("a", deps=["r1"]),
                                         _release("r2", deps=["a"])], []),
            ("a chain over a runtime seam",
             [_release("r1"), _release("r2", runtime_deps=["r1"])], []),
            ("an orphan", [_release("r1"), _release("r2")], [orphan]),
            ("an orphan with work", [_release("r1"), _node("e"), _release("r2", deps=["e"])],
             [orphan]),
            ("a hotfix beside a newer release",
             [_release("r1"), _release("r1.1", deps=["r1"]), _release("r2", deps=["r1"])],
             [("unordered releases", "r2", "neither r1.1 nor r2 depends on the other", False)]),
            ("no releases", [_node("a")], []),
        ]
        for name, nodes, expected in cases:
            with self.subTest(name):
                self.assertEqual(self._release_findings(*nodes), expected)

    def test_the_first_is_first_in_the_file_not_by_name(self):
        result = self._release_findings(_release("z"), _release("a"))
        self.assertEqual(result, [("orphan release", "a",
                                   "depends on no release; the first release is z", True)])

    def test_an_orphan_gets_no_unordered_note_as_well(self):
        """'R3 skipped R2' is the note's case; an orphan already says more."""
        result = self._release_findings(_release("r1"), _release("r2"), _release("r3"))
        self.assertEqual([f[:2] for f in result], [("orphan release", "r2"), ("orphan release", "r3")])

    def test_r3_skipping_r2_is_a_note(self):
        result = self._release_findings(_release("r1"), _release("r2", deps=["r1"]),
                                        _release("r3", deps=["r1"]))
        self.assertEqual(result, [("unordered releases", "r3",
                                   "neither r2 nor r3 depends on the other", False)])


if __name__ == "__main__":
    unittest.main()
