"""B0: one token set drives every view (D-11: Weaver's own, D-13: CSS variables)."""
import colorsys
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "weaver"
HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")


def _hue(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


class TestTokens(unittest.TestCase):
    def test_no_raw_colour_outside_the_token_module(self):
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name == "tokens.py":
                continue
            with self.subTest(path.name):
                self.assertEqual(HEX.findall(path.read_text(encoding="utf-8")), [])

    def test_css_block_declares_every_token(self):
        from weaver.tokens import LIGHT, css_variables
        css = css_variables()
        for name, value in LIGHT.items():
            with self.subTest(name):
                self.assertIn(f"--wv-{name}: {value};", css)

    def test_dark_overrides_only_known_tokens(self):
        from weaver.tokens import DARK, LIGHT
        self.assertLessEqual(set(DARK), set(LIGHT))

    def test_scope_hues_follow_the_task_dimension_glyphs(self):
        """The Task Dimension glyph hues: I blue, L green, P yellow, U orange, G red: cool to hot."""
        from weaver.tokens import LIGHT
        bands = {"I": (200, 250), "L": (90, 160), "P": (40, 60), "U": (15, 35), "G": (-10, 10)}
        for code, (low, high) in bands.items():
            with self.subTest(code):
                hue = _hue(LIGHT[f"scope-{code}"])
                hue = hue - 360 if hue > 300 else hue
                self.assertTrue(low <= hue <= high, f"scope {code} hue {hue:.0f}")

    def test_status_fills_differ_in_lightness_not_only_hue(self):
        """B3: red-green colour blindness keeps lightness, so the fills must step in it."""
        from weaver.model import STATUSES
        from weaver.tokens import LIGHT

        def lightness(c: str) -> float:
            r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        values = sorted(lightness(LIGHT[f"status-{s}"]) for s in STATUSES)
        gaps = [b - a for a, b in zip(values, values[1:])]
        self.assertGreaterEqual(min(gaps), 0.04, values)

    def test_graphviz_uses_the_token_values(self):
        from weaver.dot import COMPLEXITY_COLOUR, SCOPE_TEXT_COLOUR, _FILL
        from weaver.tokens import LIGHT

        def key(c: str) -> str:
            return "unknown" if c == "?" else c
        self.assertEqual(SCOPE_TEXT_COLOUR, {c: LIGHT[f"scope-text-{key(c)}"] for c in "ILPUG?"})
        self.assertEqual(COMPLEXITY_COLOUR, {c: LIGHT[f"complexity-{key(c)}"] for c in "TEMHN?"})
        self.assertEqual(_FILL, {s: LIGHT[f"status-{s}"] for s in _FILL})

    def test_scope_text_keeps_the_scope_hues(self):
        from weaver.tokens import LIGHT
        for code in "ILPUG":
            with self.subTest(code):
                bright, text = _hue(LIGHT[f"scope-{code}"]), _hue(LIGHT[f"scope-text-{code}"])
                self.assertLess(min(abs(bright - text), 360 - abs(bright - text)), 15)

    def test_scope_text_is_readable_on_the_canvas(self):
        """WCAG AA for normal text: 4.5:1 against the white canvas."""
        from weaver.tokens import LIGHT

        def luminance(c: str) -> float:
            def channel(v: float) -> float:
                return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
            r, g, b = (channel(int(c[i:i + 2], 16) / 255) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        canvas = luminance(LIGHT["canvas"])
        for code in ["I", "L", "P", "U", "G", "unknown"]:
            with self.subTest(code):
                text = luminance(LIGHT[f"scope-text-{code}"])
                self.assertGreaterEqual((canvas + 0.05) / (text + 0.05), 4.5)

    def test_stylesheet_drives_the_graph_through_classes(self):
        """B2: every encoded value has a rule reading its token; Graphviz's attributes
        only remain as the fallback for the standalone SVG and the PDF."""
        from weaver.html import _STYLE
        expected = (
            [f"#viewport g.node.status-{s} :is(polygon, path):not([fill=\"none\"]) "
             f"{{ fill: var(--wv-status-{s}); }}" for s in ("todo", "doing", "done", "blocked")]
            + [f"#viewport g.node.complexity-{c} :is(polygon, path) "
               f"{{ stroke: var(--wv-complexity-{c}); }}" for c in ("T", "E", "M", "H", "N", "unknown")]
            + [f"#viewport g.node.scope-{c}:not(.kind-release) text "
               f"{{ fill: var(--wv-scope-text-{c}); }}" for c in ("I", "L", "P", "U", "G", "unknown")]
            + ["#viewport g.node.kind-release text { fill: var(--wv-release); font-weight: bold; }",
               "#viewport g.cluster.lane > :is(polygon, path) { stroke: var(--wv-lane); }",
               "#viewport g.cluster.lane > text { fill: var(--wv-lane-text); }"])
        for rule in expected:
            with self.subTest(rule):
                self.assertIn(rule, _STYLE)

    def test_scope_rules_leave_releases_alone(self):
        """A release keeps its purple (D-15), whatever its scope."""
        from weaver.html import _STYLE
        scope_rules = [ln for ln in _STYLE.splitlines() if "g.node.scope-" in ln]
        self.assertEqual(len(scope_rules), 6)
        for rule in scope_rules:
            with self.subTest(rule):
                self.assertIn(":not(.kind-release) text ", rule)

    def test_hover_and_focus_come_after_the_graph_rules(self):
        from weaver.html import _STYLE
        last_graph_rule = _STYLE.rindex("#viewport g.cluster.lane")
        self.assertGreater(_STYLE.index("g.node:hover"), last_graph_rule)
        self.assertGreater(_STYLE.index("g.node:focus-visible"), last_graph_rule)

    def test_page_and_pdf_carry_the_variables(self):
        from weaver import parse_plan
        from weaver.html import build_html
        from weaver.pdf import _CSS as PDF_STYLE
        plan = parse_plan({"plan": {"schema": 1, "title": "T"}, "node": [{"id": "a", "title": "x"}]})
        self.assertIn("--wv-scope-I:", build_html(plan, "<svg></svg>"))
        self.assertIn("--wv-ink:", PDF_STYLE)


if __name__ == "__main__":
    unittest.main()
