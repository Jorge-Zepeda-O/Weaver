import tempfile
import unittest
from pathlib import Path

from weaver import Dep, PlanError, load_plan, parse_plan

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "weaver_plan.toml"


def _plan(*nodes: dict, **header: str) -> dict:
    return {"plan": {"title": "T", **header}, "node": list(nodes)}


def _errors(data: dict) -> list[str]:
    try:
        parse_plan(data)
    except PlanError as exc:
        return exc.errors
    raise AssertionError("expected PlanError, the plan was accepted")


class TestValidPlans(unittest.TestCase):
    def test_example_plan_loads(self):
        plan = load_plan(EXAMPLE)
        self.assertEqual([n.id for n in plan.nodes], ["A0", "A1", "A2", "A3", "A4", "A5", "M1"])

    def test_defaults_apply(self):
        node = parse_plan(_plan({"id": "a", "title": "x"})).node("a")
        self.assertEqual((node.kind, node.status, node.owner, node.notes, node.deps),
                         ("atom", "todo", "", "", ()))

    def test_seam_type_follows_the_key(self):
        plan = parse_plan(_plan({"id": "a", "title": "x"}, {"id": "b", "title": "y"},
                                {"id": "c", "title": "z", "deps": ["a"], "runtime_deps": ["b"]}))
        self.assertEqual(plan.node("c").deps, (Dep("a", "build"), Dep("b", "runtime")))

    def test_edges_point_from_dependency_to_dependent(self):
        plan = parse_plan(_plan({"id": "a", "title": "x"}, {"id": "b", "title": "y", "deps": ["a"]}))
        (edge,) = plan.edges()
        self.assertEqual((edge.source, edge.target, edge.seam), ("a", "b", "build"))


class TestInvalidPlans(unittest.TestCase):
    def test_each_defect_is_named(self):
        ok = {"id": "a", "title": "x"}
        cases = [
            ("missing [plan]", {"node": [ok]}, "missing [plan] table"),
            ("missing title", {"plan": {}, "node": [ok]}, "[plan]: missing 'title'"),
            ("blank title", _plan(ok, title=" "), "'title' must be a non-empty string"),
            ("no nodes", {"plan": {"title": "T"}}, "no [[node]] entries"),
            ("unknown top key", {**_plan(ok), "nodes": []}, "unknown top-level key 'nodes'"),
            ("unknown node key", _plan({**ok, "dep": ["b"]}), "unknown key 'dep'"),
            ("bad id", _plan({"id": "a b", "title": "x"}), "'id' must match"),
            ("bad kind", _plan({**ok, "kind": "merger"}), "'kind' must be one of atom, merge"),
            ("bad status", _plan({**ok, "status": "wip"}), "'status' must be one of"),
            ("deps not a list", _plan({**ok, "deps": "b"}), "'deps' must be a list"),
            ("duplicate id", _plan(ok, dict(ok)), "duplicate node id 'a'"),
            ("unknown dep", _plan({**ok, "deps": ["zz"]}), "unknown dependency 'zz'"),
            ("self dep", _plan({**ok, "deps": ["a"]}), "depends on itself"),
            ("both seam types", _plan({"id": "b", "title": "y"},
                                      {**ok, "deps": ["b"], "runtime_deps": ["b"]}),
             "'b' listed more than once"),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                self.assertTrue(any(expected in e for e in _errors(data)), _errors(data))

    def test_cycle_is_reported_with_its_path(self):
        data = _plan({"id": "a", "title": "x", "deps": ["c"]},
                     {"id": "b", "title": "y", "deps": ["a"]},
                     {"id": "c", "title": "z", "deps": ["b"]})
        (error,) = _errors(data)
        prefix = "dependency cycle: "
        self.assertTrue(error.startswith(prefix), error)
        path = error.removeprefix(prefix).split(" -> ")
        edges = {("c", "a"), ("a", "b"), ("b", "c")}  # dependency -> dependent
        self.assertEqual(path[0], path[-1], "the reported path must close")
        self.assertEqual(set(path), {"a", "b", "c"})
        for step in zip(path, path[1:]):
            self.assertIn(step, edges, f"{step} is not an edge of the plan")

    def test_all_errors_are_reported_at_once(self):
        data = _plan({"id": "a", "title": "x", "kind": "nope"}, {"id": "b", "title": "y", "status": "nope"})
        self.assertEqual(len(_errors(data)), 2)

    def test_invalid_toml_is_a_plan_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text("[plan\n", encoding="utf-8")
            with self.assertRaises(PlanError) as ctx:
                load_plan(path)
            self.assertIn("not valid TOML", ctx.exception.errors[0])


if __name__ == "__main__":
    unittest.main()
