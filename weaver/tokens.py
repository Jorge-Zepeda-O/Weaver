"""Design tokens: every colour Weaver draws with, in one place (B0; D-11, D-13).

Weaver's own set, never another project's palette. The page reads them as CSS
variables (``--wv-<name>``); Graphviz and the PDF get the same values, because
the standalone SVG and the PDF have no page stylesheet to inherit from.
"""
from __future__ import annotations

LIGHT: dict[str, str] = {
    # Page chrome.
    "bg": "#f8fafc", "fg": "#0f172a", "muted": "#475569", "panel": "#ffffff",
    "border": "#cbd5e1", "accent": "#2563eb", "focus": "#2563eb",
    # The graph canvas: always light, because Graphviz paints the nodes for it.
    "canvas": "#ffffff", "ink": "#334155", "lane": "#94a3b8", "lane-text": "#475569",
    # The card's rules (A3-7): the line under the header and the divider before the codes.
    "rule": "#94a3b8",
    # Status fills step in lightness as well as hue (todo > done > doing > blocked),
    # so they stay apart without full colour vision; the symbol carries status anyway (B3).
    "status-todo": "#ffffff", "status-done": "#d1fae5",
    "status-doing": "#bfdbfe", "status-blocked": "#fca5a5",
    # Scope: cool to hot, the hues of the Task Dimension glyphs (blue green yellow orange red).
    # Unknown ranks worst, so it sits past global. Bright shades for swatches and panel cells
    # (and, later, text on a dark canvas); the darker text shades meet WCAG AA on white.
    "scope-I": "#2563eb", "scope-L": "#16a34a", "scope-P": "#ca8a04",
    "scope-U": "#ea580c", "scope-G": "#dc2626", "scope-unknown": "#7f1d1d",
    "scope-text-I": "#1d4ed8", "scope-text-L": "#15803d", "scope-text-P": "#a16207",
    "scope-text-U": "#c2410c", "scope-text-G": "#b91c1c", "scope-text-unknown": "#7f1d1d",
    # Complexity: the border's colour, calm to alarming like its glyphs (white, white, orange,
    # red, explosion). Unknown ranks worst, as novel.
    "complexity-T": "#94a3b8", "complexity-E": "#64748b", "complexity-M": "#ea580c",
    "complexity-H": "#dc2626", "complexity-N": "#7f1d1d", "complexity-unknown": "#7f1d1d",
    # Purple is in no scope colour, so a release's text stays unique.
    "release": "#7e22ce",
    # Print: near-black text, a muted grey for keys and metadata.
    "print-ink": "#111111", "print-muted": "#555555",
}

# Dark mode covers the page chrome only; the graph canvas stays light (dark graphs: v0.2.1+).
DARK: dict[str, str] = {
    "bg": "#0b1120", "fg": "#e2e8f0", "muted": "#94a3b8", "panel": "#1e293b",
    "border": "#334155", "accent": "#60a5fa",
}


def _declarations(tokens: dict[str, str]) -> str:
    return " ".join(f"--wv-{name}: {value};" for name, value in tokens.items())


def css_variables(dark: bool = True) -> str:
    """``:root`` declarations for every token, plus the dark overrides when wanted."""
    css = f":root {{ {_declarations(LIGHT)} }}\n"
    if dark:
        css += f"@media (prefers-color-scheme: dark) {{ :root {{ {_declarations(DARK)} }} }}\n"
    return css
