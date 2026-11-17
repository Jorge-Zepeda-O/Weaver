"""CLI (merge event M1): ``python -m weaver build PLAN.toml -o out/``.

Exit codes: 0 built · 1 the plan is invalid · 2 wrong invocation or unreadable file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .load import PlanError, load_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weaver", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="render a plan file to SVG, HTML, Markdown and PDF")
    build.add_argument("plan", type=Path, help="the plan file (TOML)")
    build.add_argument("-o", "--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)

    if not args.plan.is_file():
        print(f"weaver: no such plan file: {args.plan}", file=sys.stderr)
        return 2
    try:
        plan = load_plan(args.plan)
    except PlanError as exc:
        print(f"weaver: {args.plan}: {exc}", file=sys.stderr)
        return 1

    from .dot import render_svg
    from .html import build_html
    from .markdown import to_markdown
    from .pdf import build_pdf

    args.out.mkdir(parents=True, exist_ok=True)
    svg = render_svg(plan)
    outputs = {
        "plan.svg": svg,
        "PLAN.html": build_html(plan, svg),
        "PLAN.md": to_markdown(plan),
    }
    for name, text in outputs.items():
        (args.out / name).write_text(text, encoding="utf-8")
    build_pdf(plan, svg, args.out / "PLAN.pdf")

    print(f"weaver: {len(plan.nodes)} nodes, {len(plan.edges())} edges → "
          f"{', '.join([*outputs, 'PLAN.pdf'])} in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
