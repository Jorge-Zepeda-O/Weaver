import tempfile
import unittest
from pathlib import Path

from weaver import Dep, PlanError, load_plan, parse_plan

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "weaver_plan.toml"


def _plan(*nodes: dict, **header: str) -> dict:
    return {"plan": {"schema": 1, "title": "T", **header}, "node": list(nodes)}


def _errors(data: dict) -> list[str]:
    try:
        parse_plan(data)
    except PlanError as exc:
        return exc.errors
    raise AssertionError("expected PlanError, the plan was accepted")


class TestValidPlans(unittest.TestCase):
    def test_example_plan_loads(self):
        plan = load_plan(EXAMPLE)
        self.assertEqual([n.id for n in plan.nodes], ["A0", "A1", "A2", "A3", "A4", "A5", "M1", "V1"])

    def test_defaults_apply(self):
        node = parse_plan(_plan({"id": "a", "title": "x"})).node("a")
        self.assertEqual(
            (node.kind, node.status, node.group, node.notes, node.deps, node.scope, node.amount,
             node.complexity, node.verify, node.decisions),
            ("atom", "todo", "", "", (), "", "", "", "", ()))

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
            ("missing title", {"plan": {"schema": 1}, "node": [ok]}, "[plan]: missing 'title'"),
            ("blank title", _plan(ok, title=" "), "'title' must be a non-empty string"),
            ("no nodes", {"plan": {"schema": 1, "title": "T"}}, "no [[node]] entries"),
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


class TestSchemaV1(unittest.TestCase):
    ok = {"id": "a", "title": "x"}

    def test_schema_version_is_required_and_must_be_known(self):
        cases = [
            ("missing", {"plan": {"title": "T"}, "node": [self.ok]},
             "[plan]: missing 'schema' (this version of weaver reads schema = 1, 2 or 3)"),
            ("unknown version", _plan(self.ok, schema=4),
             "[plan]: unsupported schema 4 (this version of weaver reads schema = 1, 2 or 3)"),
            ("zero", _plan(self.ok, schema=0), "[plan]: unsupported schema 0"),
            ("string", _plan(self.ok, schema="1"), "[plan]: 'schema' must be an integer"),
            ("bool", _plan(self.ok, schema=True), "[plan]: 'schema' must be an integer"),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                errors = _errors(data)
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_plan_header_fields(self):
        plan = parse_plan(_plan(self.ok, goal="Ship it.", caption="c"))
        self.assertEqual((plan.schema, plan.goal, plan.caption), (1, "Ship it.", "c"))
        self.assertTrue(any("'goal' must be a string" in e for e in _errors(_plan(self.ok, goal=3))))

    def test_owner_points_to_its_replacement(self):
        errors = _errors(_plan({**self.ok, "owner": "main"}))
        self.assertIn("node 'a': unknown key 'owner' (renamed to 'group' in schema 1)", errors)

    def test_node_fields(self):
        node = parse_plan(_plan({**self.ok, "group": "sub-1", "verify": "tests/test_a.py",
                                 "decisions": ["D-3", "other:D-22"]})).node("a")
        self.assertEqual((node.group, node.verify, node.decisions),
                         ("sub-1", "tests/test_a.py", ("D-3", "other:D-22")))

    def test_every_dimension_code_is_accepted(self):
        cases = [("scope", "ILPUG?"), ("amount", "1FNBS?"), ("complexity", "TEMHN?")]
        for field, codes in cases:
            for code in codes:
                with self.subTest(field=field, code=code):
                    node = parse_plan(_plan({**self.ok, field: code})).node("a")
                    self.assertEqual(getattr(node, field), code)

    def test_bad_values_are_named(self):
        cases = [
            ("scope code", {"scope": "X"}, "'scope' must be one of I, L, P, U, G, ?"),
            ("amount code", {"amount": 1}, "'amount' must be one of 1, F, N, B, S, ?"),
            ("complexity code", {"complexity": "m"}, "'complexity' must be one of T, E, M, H, N, ?"),
            ("group", {"group": 1}, "'group' must be a string"),
            ("verify", {"verify": ["x"]}, "'verify' must be a string"),
            ("decisions not a list", {"decisions": "D-3"}, "'decisions' must be a list"),
            ("decision handle", {"decisions": ["D3"]}, "'D3' is not a decision handle"),
            ("other handle kind", {"decisions": ["proj:T-1"]}, "'proj:T-1' is not a decision handle"),
        ]
        for name, extra, expected in cases:
            with self.subTest(name):
                errors = _errors(_plan({**self.ok, **extra}))
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_a_merge_or_release_without_verify_is_unguarded(self):
        cases = [("merge", "", True), ("merge", "tests/test_m.py", False), ("atom", "", False),
                 ("release", "", True), ("release", "tests/test_r.py", False)]
        for kind, verify, unguarded in cases:
            with self.subTest(kind=kind, verify=verify):
                node = parse_plan(_plan({**self.ok, "kind": kind, "verify": verify},
                                        schema=2)).node("a")
                self.assertIs(node.unguarded, unguarded)

    def test_groups_in_order_of_first_appearance(self):
        plan = parse_plan(_plan({"id": "a", "title": "x", "group": "two"},
                                {"id": "b", "title": "y"},
                                {"id": "c", "title": "z", "group": "one"},
                                {"id": "d", "title": "w", "group": "two"}))
        self.assertEqual(plan.groups(), ("two", "one"))

    def test_status_label_is_symbol_and_word(self):
        for status, expected in [("todo", "○ todo"), ("doing", "◐ doing"), ("done", "✓ done"),
                                 ("blocked", "✕ blocked")]:
            with self.subTest(status):
                node = parse_plan(_plan({**self.ok, "status": status})).node("a")
                self.assertEqual(node.status_label(), expected)

    def test_dimension_label(self):
        cases = [({}, ""), ({"scope": "L"}, "↕L ↔- ⤓-"),
                 ({"scope": "?", "amount": "F", "complexity": "N"}, "↕? ↔F ⤓N")]
        for extra, expected in cases:
            with self.subTest(extra):
                node = parse_plan(_plan({**self.ok, **extra})).node("a")
                self.assertEqual(node.dimension_label(), expected)

    def test_example_plan_uses_schema_v2(self):
        """R2: the example shows the release kind, so it declares schema 2."""
        plan = load_plan(EXAMPLE)
        self.assertEqual(plan.schema, 2)
        self.assertEqual([n.id for n in plan.nodes if n.kind == "release"], ["V1"])
        self.assertTrue(plan.goal)
        for node in plan.nodes:
            with self.subTest(node.id):
                self.assertTrue(node.group and node.verify and node.dimension_label(), node)


class TestSchemaV2(unittest.TestCase):
    """D-15: kind = "release" is new in schema 2; schema 1 plans keep working."""
    release = {"id": "r", "title": "v1", "kind": "release", "verify": "tag pushed"}

    def test_both_known_versions_load(self):
        for version in (1, 2):
            with self.subTest(schema=version):
                plan = parse_plan(_plan({"id": "a", "title": "x"}, schema=version))
                self.assertEqual(plan.schema, version)

    def test_release_loads_in_schema_2(self):
        self.assertEqual(parse_plan(_plan(self.release, schema=2)).node("r").kind, "release")

    def test_release_in_schema_1_names_the_version_it_needs(self):
        errors = _errors(_plan(self.release, schema=1))
        self.assertIn("node 'r': kind 'release' needs schema = 2", errors)

    def test_unknown_kind_lists_all_three(self):
        errors = _errors(_plan({"id": "a", "title": "x", "kind": "merger"}, schema=2))
        self.assertTrue(any("'kind' must be one of atom, merge, release" in e for e in errors), errors)


class TestFiles(unittest.TestCase):
    """A3-1: `files` per node is new in schema 3."""
    base = {"id": "a", "title": "x"}

    def _files(self, files, schema=3):
        return parse_plan(_plan({**self.base, "files": files}, schema=schema)).node("a").files

    def test_parses(self):
        self.assertEqual(self._files(["weaver/html.py", "tests/test_html.py"]),
                         ("weaver/html.py", "tests/test_html.py"))

    def test_defaults_to_empty(self):
        for schema in (1, 2, 3):
            with self.subTest(schema=schema):
                self.assertEqual(parse_plan(_plan(self.base, schema=schema)).node("a").files, ())

    def test_schema_gate(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                errors = _errors(_plan({**self.base, "files": ["a.py"]}, schema=schema))
                self.assertIn("node 'a': field 'files' needs schema = 3", errors)
        self.assertEqual(self._files(["a.py"], schema=3), ("a.py",))

    def test_bad_types_rejected(self):
        for name, value in [("string", "a.py"), ("number", 3), ("list of numbers", [1]),
                            ("empty string", [""]), ("blank string", ["  "]),
                            ("mixed", ["a.py", 2]), ("empty after normalising", ["./"]),
                            ("root only", ["/"])]:
            with self.subTest(name):
                errors = _errors(_plan({**self.base, "files": value}, schema=3))
                self.assertIn("node 'a': 'files' must be a list of non-empty strings", errors)

    def test_paths_are_normalised(self):
        self.assertEqual(self._files(["./a/b.py", "a/", "./c/"]), ("a/b.py", "a", "c"))

    def test_duplicates_in_one_node_count_once(self):
        self.assertEqual(self._files(["a.py", "./a.py", "b.py", "a.py"]), ("a.py", "b.py"))


if __name__ == "__main__":
    unittest.main()
