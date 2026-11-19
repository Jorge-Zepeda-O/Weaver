"""CLI (merge event M1): ``python -m weaver build PLAN.toml -o out/``.

Exit codes: 0 built · 1 the plan is invalid · 2 wrong invocation or unreadable file ·
3 with --strict: an unacknowledged overlap, a stale acknowledgement, or a strict finding
(an unassessed node, …).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .load import PlanError, load_plan
from .checks import findings
from .model import acknowledgement_report, overlaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weaver", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="render a plan file to SVG, HTML, Markdown and PDF")
    build.add_argument("plan", type=Path, help="the plan file (TOML)")
    build.add_argument("-o", "--out", type=Path, required=True, help="output directory")
    build.add_argument("--strict", action="store_true",
                       help="exit 3 when two groups touch the same file and no [[overlap]] "
                            "entry acknowledges it (the build still runs)")
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

    found = overlaps(plan)
    for overlap in found:
        print(f"weaver: overlap: {overlap.describe(plan)}", file=sys.stderr)
    stale, history = acknowledgement_report(plan)
    for entry in stale:
        print(f"weaver: stale acknowledgement: {entry.describe()}", file=sys.stderr)
    checked = findings(plan)
    for finding in checked:
        print(f"weaver: {finding.describe()}", file=sys.stderr)
    acked = sum(overlap.acknowledged for overlap in found)
    stale_entries = len({entry.entry for entry in stale})
    suffix = (f", {len(found)} overlap{'s' * (len(found) != 1)}"
              + (f" ({acked} acknowledged)" if acked else "")) if found else ""
    if stale_entries:
        suffix += f", {stale_entries} stale acknowledgement{'s' * (stale_entries != 1)}"
    if history:
        suffix += f", {history} acknowledgement{'s' * (history != 1)} now history (prunable)"
    for check in dict.fromkeys(finding.check for finding in checked):
        suffix += f", {sum(finding.check == check for finding in checked)} {check}"
    print(f"weaver: {len(plan.nodes)} nodes, {len(plan.edges())} edges → "
          f"{', '.join([*outputs, 'PLAN.pdf'])} in {args.out}{suffix}")
    failed = acked < len(found) or stale_entries or any(f.strict for f in checked)
    return 3 if args.strict and failed else 0


if __name__ == "__main__":
    sys.exit(main())
