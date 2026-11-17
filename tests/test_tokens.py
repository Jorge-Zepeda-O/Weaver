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
        from weaver.dot import SCOPE_COLOUR, _FILL
        from weaver.tokens import LIGHT
        self.assertEqual(SCOPE_COLOUR, {c: LIGHT[f"scope-{c if c != '?' else 'unknown'}"]
                                        for c in "ILPUG?"})
        self.assertEqual(_FILL, {s: LIGHT[f"status-{s}"] for s in _FILL})

    def test_page_and_pdf_carry_the_variables(self):
        from weaver import parse_plan
        from weaver.html import build_html
        from weaver.pdf import _CSS as PDF_STYLE
        plan = parse_plan({"plan": {"schema": 1, "title": "T"}, "node": [{"id": "a", "title": "x"}]})
        self.assertIn("--wv-scope-I:", build_html(plan, "<svg></svg>"))
        self.assertIn("--wv-ink:", PDF_STYLE)


if __name__ == "__main__":
    unittest.main()
