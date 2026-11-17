"""Behaviour of the HTML view's gesture core, run under Node.

The core (``weaver.html._GESTURES``) is DOM-free: pointer events go in, ``pan``
and ``zoom`` calls and a click verdict come out. Each test replays a gesture and
checks what the page would do. Node is a test-only dependency; without it these
tests skip loudly rather than pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest

NODE = shutil.which("node")

# Replays [op, args] steps against makeGestures and prints what happened.
_DRIVER = """
const steps = JSON.parse(require("fs").readFileSync(0, "utf8"));
const log = [];
const g = makeGestures({
  pan: (dx, dy) => log.push(["pan", dx, dy]),
  zoom: (f, x, y) => log.push(["zoom", f, x, y]),
});
for (const [op, a] of steps) {
  if (op === "click") log.push(["click", g.clickAllowed()]);
  else g[op]({ id: 1, x: 0, y: 0, type: "mouse", primary: true, ...a });
}
process.stdout.write(JSON.stringify(log));
"""


def replay(steps: list) -> list:
    from weaver.html import _GESTURES  # deferred: RED until the core exists
    result = subprocess.run([NODE, "-e", _GESTURES + _DRIVER], input=json.dumps(steps),
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def clicks(log: list) -> list[bool]:
    return [entry[1] for entry in log if entry[0] == "click"]


def total_pan(log: list) -> tuple[float, float]:
    pans = [entry for entry in log if entry[0] == "pan"]
    return sum(p[1] for p in pans), sum(p[2] for p in pans)


def touch(id_: int, x: float, y: float, primary: bool) -> dict:
    return {"id": id_, "x": x, "y": y, "type": "touch", "primary": primary}


@unittest.skipUnless(NODE, "node not found: the gesture tests cannot run")
class ClickTest(unittest.TestCase):
    def test_tap_opens(self):
        self.assertEqual(clicks(replay([["down", {}], ["up", {}], ["click", None]])), [True])

    def test_click_after_a_drag_is_suppressed(self):
        log = replay([["down", {}], ["move", {"x": 30}], ["up", {"x": 30}], ["click", None]])
        self.assertEqual(clicks(log), [False])

    def test_drag_with_no_click_does_not_eat_the_next_tap(self):
        # The swallowed-click bug: a drag released off the graph fires no click,
        # and the next genuine tap must still open its node.
        log = replay([["down", {}], ["move", {"x": 30}], ["up", {"x": 30}],
                      ["down", {"x": 50}], ["up", {"x": 50}], ["click", None]])
        self.assertEqual(clicks(log), [True])

    def test_wobble_threshold_depends_on_pointer_type(self):
        # 8px is a deliberate drag for a mouse and a wobbly tap for a finger.
        for kind, opens in [("mouse", False), ("touch", True)]:
            with self.subTest(kind=kind):
                log = replay([["down", {"type": kind}], ["move", {"type": kind, "x": 8}],
                              ["up", {"type": kind, "x": 8}], ["click", None]])
                self.assertEqual(clicks(log), [opens])

    def test_click_after_a_pinch_is_suppressed(self):
        log = replay([["down", touch(1, 100, 100, True)], ["down", touch(2, 200, 100, False)],
                      ["move", touch(2, 260, 100, False)],
                      ["up", touch(2, 260, 100, False)], ["up", touch(1, 100, 100, True)],
                      ["click", None]])
        self.assertEqual(clicks(log), [False])


@unittest.skipUnless(NODE, "node not found: the gesture tests cannot run")
class PanTest(unittest.TestCase):
    def test_drag_pans_by_the_full_displacement(self):
        log = replay([["down", {}], ["move", {"x": 10, "y": 3}], ["move", {"x": 25, "y": -4}],
                      ["up", {"x": 25, "y": -4}]])
        self.assertEqual(total_pan(log), (25, -4))

    def test_movement_inside_the_threshold_does_not_pan(self):
        log = replay([["down", {}], ["move", {"x": 2, "y": 2}], ["up", {"x": 2, "y": 2}]])
        self.assertEqual(total_pan(log), (0, 0))


@unittest.skipUnless(NODE, "node not found: the gesture tests cannot run")
class PinchTest(unittest.TestCase):
    def pinch(self, x2_end: float) -> list:
        return replay([["down", touch(1, 100, 100, True)], ["down", touch(2, 200, 100, False)],
                       ["move", touch(2, x2_end, 100, False)]])

    def test_spreading_fingers_zooms_in_at_their_midpoint(self):
        zooms = [e for e in self.pinch(300) if e[0] == "zoom"]
        self.assertEqual(len(zooms), 1)
        _, factor, x, y = zooms[0]
        self.assertAlmostEqual(factor, 0.5)  # distance doubled: half the width shown
        self.assertEqual((x, y), (200, 100))

    def test_pinching_fingers_zooms_out(self):
        zooms = [e for e in self.pinch(150) if e[0] == "zoom"]
        self.assertAlmostEqual(zooms[0][1], 2.0)

    def test_two_finger_drag_pans_by_the_midpoint(self):
        log = replay([["down", touch(1, 100, 100, True)], ["down", touch(2, 200, 100, False)],
                      ["move", touch(1, 100, 140, True)], ["move", touch(2, 200, 140, False)]])
        self.assertEqual(total_pan(log), (0, 40))

    def test_lifting_one_finger_continues_as_a_drag_without_a_jump(self):
        log = replay([["down", touch(1, 100, 100, True)], ["down", touch(2, 200, 100, False)],
                      ["up", touch(2, 200, 100, False)],
                      ["move", touch(1, 103, 100, True)]])
        self.assertEqual(total_pan(log), (3, 0))  # gesture already moved: no threshold, no jump

    def test_a_lost_pointerup_does_not_turn_the_next_press_into_a_pinch(self):
        # A pointerup can be lost (released outside the window); a new primary
        # press starts a new gesture instead of pairing with the stale pointer.
        # Apart, so a phantom pinch would have a distance to zoom by.
        log = replay([["down", {"id": 1}], ["down", {"id": 2, "x": 100}],
                      ["move", {"id": 2, "x": 130}], ["up", {"id": 2, "x": 130}], ["click", None]])
        self.assertEqual([e for e in log if e[0] == "zoom"], [])
        self.assertEqual(clicks(log), [False])  # it was an ordinary drag


if __name__ == "__main__":
    unittest.main()
