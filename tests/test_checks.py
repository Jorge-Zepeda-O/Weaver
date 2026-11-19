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


if __name__ == "__main__":
    unittest.main()
