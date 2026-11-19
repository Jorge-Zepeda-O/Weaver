"""A3-2: the file-overlap check, as a truth table over the ruled cases."""
import unittest

from weaver import parse_plan
from weaver.model import Overlap, overlaps


def _node(node_id: str, group: str = "", files=("f.py",), status: str = "todo", deps=(),
          runtime_deps=()) -> dict:
    return {"id": node_id, "title": node_id, "group": group, "files": list(files),
            "status": status, "deps": list(deps), "runtime_deps": list(runtime_deps)}


def _overlaps(*nodes: dict) -> tuple[Overlap, ...]:
    return overlaps(parse_plan({"plan": {"schema": 3, "title": "T"}, "node": list(nodes)}))


class TestOverlaps(unittest.TestCase):
    def test_truth_table(self):
        clash = (Overlap("f.py", "a", "b"),)
        cases = [
            ("same group, same file", [_node("a", "g"), _node("b", "g")], ()),
            ("different groups, independent", [_node("a", "g"), _node("b", "h")], clash),
            ("different groups, direct dep", [_node("a", "g"), _node("b", "h", deps=["a"])], ()),
            ("different groups, direct runtime dep",
             [_node("a", "g"), _node("b", "h", runtime_deps=["a"])], ()),
            ("different groups, transitive dep",
             [_node("a", "g"), _node("m", "k", files=[], deps=["a"]),
              _node("b", "h", deps=["m"])], ()),
            # A4-1 (ruled 20261119): v0.3 called this history; done is not merged (D-21).
            ("both done, neither landed",
             [_node("a", "g", status="done"), _node("b", "h", status="done")], clash),
            ("one done", [_node("a", "g", status="done"), _node("b", "h")], clash),
            ("no group vs group", [_node("a"), _node("b", "h")], clash),
            ("two ungrouped nodes are separate groups", [_node("a"), _node("b")], clash),
            ("folder does not match its files",
             [_node("a", "g", files=["src"]), _node("b", "h", files=["src/x.py"])], ()),
            ("normalised paths match",
             [_node("a", "g", files=["./f.py"]), _node("b", "h", files=["f.py"])], clash),
            ("no files", [_node("a", "g", files=[]), _node("b", "h", files=[])], ()),
        ]
        for name, nodes, expected in cases:
            with self.subTest(name):
                self.assertEqual(_overlaps(*nodes), expected)

    def test_three_groups_give_one_overlap_per_pair(self):
        result = _overlaps(_node("a", "g"), _node("b", "h"), _node("c", "i"))
        self.assertEqual(result, (Overlap("f.py", "a", "b"), Overlap("f.py", "a", "c"),
                                  Overlap("f.py", "b", "c")))

    def test_order_is_file_then_plan_order(self):
        result = _overlaps(_node("z", "g", files=["b.py", "a.py"]),
                           _node("y", "h", files=["a.py", "b.py"]))
        self.assertEqual(result, (Overlap("a.py", "z", "y"), Overlap("b.py", "z", "y")))



class TestAcknowledged(unittest.TestCase):
    """A3-3: an acknowledged overlap is still reported, carrying its reason; it never hides."""

    def _plan(self, *acks: dict, nodes=None):
        nodes = nodes or [_node("a", "g"), _node("b", "h"), _node("c", "i")]
        return parse_plan({"plan": {"schema": 3, "title": "T"}, "node": nodes, "overlap": list(acks)})

    def test_acknowledged_overlap_is_still_reported_with_its_reason(self):
        plan = self._plan({"file": "f.py", "nodes": ["a", "b"], "reason": "different hunks"},
                          nodes=[_node("a", "g"), _node("b", "h")])
        self.assertEqual(overlaps(plan), (Overlap("f.py", "a", "b", "different hunks"),))
        self.assertTrue(overlaps(plan)[0].acknowledged)

    def test_unacknowledged_overlap_has_no_reason(self):
        (overlap,) = overlaps(self._plan(nodes=[_node("a", "g"), _node("b", "h")]))
        self.assertEqual(overlap.reason, "")
        self.assertFalse(overlap.acknowledged)

    def test_an_entry_covers_every_pair_it_names(self):
        plan = self._plan({"file": "f.py", "nodes": ["a", "b", "c"], "reason": "r"})
        self.assertEqual([o.reason for o in overlaps(plan)], ["r", "r", "r"])

    def test_a_pair_the_entry_does_not_name_stays_unacknowledged(self):
        plan = self._plan({"file": "f.py", "nodes": ["a", "b"], "reason": "r"})
        self.assertEqual([(o.a, o.b, o.reason) for o in overlaps(plan)],
                         [("a", "b", "r"), ("a", "c", ""), ("b", "c", "")])

    def test_an_entry_acknowledges_only_its_own_file(self):
        nodes = [_node("a", "g", files=["f.py", "x.py"]), _node("b", "h", files=["f.py", "x.py"])]
        plan = self._plan({"file": "x.py", "nodes": ["a", "b"], "reason": "r"}, nodes=nodes)
        self.assertEqual([(o.file, o.reason) for o in overlaps(plan)], [("f.py", ""), ("x.py", "r")])

    def test_a_stale_entry_is_silent(self):
        """The overlap went away (here: the pair is now sequenced). Plans only grow, so an old
        acknowledgement stays valid and reports nothing."""
        nodes = [_node("a", "g"), _node("b", "h", deps=["a"])]
        plan = self._plan({"file": "f.py", "nodes": ["a", "b"], "reason": "r"}, nodes=nodes)
        self.assertEqual(overlaps(plan), ())


def _landing(node_id: str, deps=(), runtime_deps=(), status: str = "done",
             kind: str = "merge") -> dict:
    """A merge (or release) that touches no file; landing ``deps`` when it is done."""
    return {**_node(node_id, "main", files=[], status=status, deps=deps,
                    runtime_deps=runtime_deps), "kind": kind}


class TestLanding(unittest.TestCase):
    """A4-1: a node has landed when it is done and a done merge or release depends on it over
    build seams. Only a pair where BOTH sides landed is history; when one side landed, the
    overlap names where, so the honest edge is the cheap fix."""

    def _pair(self, a_status="done", b_status="todo", landings=()):
        return _overlaps(_node("a", "g", status=a_status), _node("b", "h", status=b_status),
                         *landings)

    def test_truth_table(self):
        plain = (Overlap("f.py", "a", "b"),)
        a_in_m = (Overlap("f.py", "a", "b", landed="a", landed_in="m"),)
        b_in_m = (Overlap("f.py", "a", "b", landed="b", landed_in="m"),)
        cases = [
            ("landed × todo", "done", "todo", [_landing("m", deps=["a"])], a_in_m),
            ("landed × doing", "done", "doing", [_landing("m", deps=["a"])], a_in_m),
            ("done × landed", "done", "done", [_landing("m", deps=["b"])], b_in_m),
            ("landed × landed is history", "done", "done", [_landing("m", deps=["a", "b"])], ()),
            ("landed apart is history too", "done", "done",
             [_landing("m", deps=["a"]), _landing("n", deps=["b"])], ()),
            ("done, not landed × todo", "done", "todo", [], plain),
            ("the merge is not done", "done", "todo", [_landing("m", deps=["a"], status="doing")],
             plain),
            ("a runtime seam does not land", "done", "todo",
             [_landing("m", runtime_deps=["a"])], plain),
            ("a release lands too", "done", "todo", [_landing("m", deps=["a"], kind="release")],
             a_in_m),
            ("an atom does not land", "done", "todo", [_landing("m", deps=["a"], kind="atom")],
             plain),
        ]
        for name, a_status, b_status, landings, expected in cases:
            with self.subTest(name):
                self.assertEqual(self._pair(a_status, b_status, landings), expected)

    def test_lands_through_a_transitive_build_path(self):
        result = self._pair(landings=[_landing("x", deps=["a"], kind="atom"),
                                      _landing("m", deps=["x"])])
        self.assertEqual(result, (Overlap("f.py", "a", "b", landed="a", landed_in="m"),))

    def test_names_the_first_landing_not_a_later_one(self):
        """a → m → r: a landed in m; r is only where m went next."""
        result = self._pair(landings=[_landing("r", deps=["m"], kind="release"),
                                      _landing("m", deps=["a"])])
        self.assertEqual(result, (Overlap("f.py", "a", "b", landed="a", landed_in="m"),))

    def test_two_separate_landings_name_the_first_in_plan_order(self):
        result = self._pair(landings=[_landing("n", deps=["a"]), _landing("m", deps=["a"])])
        self.assertEqual(result, (Overlap("f.py", "a", "b", landed="a", landed_in="n"),))

    def test_a_done_merge_has_landed_in_itself(self):
        nodes = [_landing("m"), _node("b", "h")]
        nodes[0]["files"] = ["f.py"]
        self.assertEqual(_overlaps(*nodes), (Overlap("f.py", "m", "b", landed="m", landed_in="m"),))


class TestLandingHint(unittest.TestCase):
    """A4-1: the hint text (ruled 20261119), after the pair and before any acknowledgement."""

    def _describe(self, *acks: dict, landings=None) -> str:
        nodes = [_node("a", "g", status="done"), _node("b", "h"),
                 *(landings if landings is not None else [_landing("m", deps=["a"])])]
        plan = parse_plan({"plan": {"schema": 3, "title": "T"}, "node": nodes,
                           "overlap": list(acks)})
        (overlap,) = overlaps(plan)
        return overlap.describe(plan)

    def test_names_the_landing_and_the_honest_edge(self):
        self.assertEqual(self._describe(),
                         "f.py — a (g) × b (h) — a landed in m: if b builds on m, add it to b's deps")

    def test_no_hint_when_nothing_landed(self):
        self.assertEqual(self._describe(landings=[]), "f.py — a (g) × b (h)")

    def test_the_hint_comes_before_the_acknowledgement(self):
        ack = {"file": "f.py", "nodes": ["a", "b"], "reason": "r"}
        self.assertEqual(self._describe(ack),
                         "f.py — a (g) × b (h) — a landed in m: if b builds on m, "
                         "add it to b's deps — acknowledged: r")

    def test_a_merge_that_landed_itself(self):
        nodes = [_landing("m"), _node("b", "h")]
        nodes[0]["files"] = ["f.py"]
        plan = parse_plan({"plan": {"schema": 3, "title": "T"}, "node": nodes})
        (overlap,) = overlaps(plan)
        self.assertEqual(overlap.describe(plan),
                         "f.py — m (main) × b (h) — m landed: if b builds on m, add it to b's deps")


if __name__ == "__main__":
    unittest.main()
