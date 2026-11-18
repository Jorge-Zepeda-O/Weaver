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
            ("both done", [_node("a", "g", status="done"), _node("b", "h", status="done")], ()),
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


if __name__ == "__main__":
    unittest.main()
