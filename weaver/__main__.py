"""CLI (merge event M1): ``python -m weaver build PLAN.toml -o out/``; also ``snapshot`` and
``history`` (A4-5).

Exit codes: 0 built · 1 the plan is invalid · 2 wrong invocation or unreadable file ·
3 unacknowledged overlaps found with --strict.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .load import PlanError, load_plan
from .model import overlaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weaver", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="render a plan file to SVG, HTML, Markdown and PDF")
    build.add_argument("plan", type=Path, help="the plan file (TOML)")
    build.add_argument("-o", "--out", type=Path, required=True, help="output directory")
    build.add_argument("--strict", action="store_true",
                       help="exit 3 when two groups touch the same file and no [[overlap]] "
                            "entry acknowledges it (the build still runs)")
    snap = commands.add_parser("snapshot", help="write PLAN_<time>/ with the plan file and its views")
    snap.add_argument("plan", type=Path, help="the plan file (TOML)")
    snap.add_argument("-d", "--dir", type=Path, required=True, help="the snapshots folder")
    past = commands.add_parser("history", help="list nodes built or started before they were "
                                               "planned, from a folder of snapshots")
    past.add_argument("dir", type=Path, help="the snapshots folder")
    args = parser.parse_args(argv)
    if args.command == "history":
        return _history(args.dir)

    if not args.plan.is_file():
        print(f"weaver: no such plan file: {args.plan}", file=sys.stderr)
        return 2
    try:
        plan = load_plan(args.plan)
    except PlanError as exc:
        print(f"weaver: {args.plan}: {exc}", file=sys.stderr)
        return 1
    if args.command == "snapshot":
        return _snapshot(args.plan, args.dir)

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
    acked = sum(overlap.acknowledged for overlap in found)
    suffix = (f", {len(found)} overlap{'s' * (len(found) != 1)}"
              + (f" ({acked} acknowledged)" if acked else "")) if found else ""
    print(f"weaver: {len(plan.nodes)} nodes, {len(plan.edges())} edges → "
          f"{', '.join([*outputs, 'PLAN.pdf'])} in {args.out}{suffix}")
    return 3 if args.strict and acked < len(found) else 0


def _snapshot(plan: Path, into: Path) -> int:
    from datetime import datetime

    from .history import snapshot
    try:
        folder = snapshot(plan, into, datetime.now())
    except FileExistsError as exc:
        print(f"weaver: a snapshot already exists: {exc.filename}", file=sys.stderr)
        return 2
    print(f"weaver: snapshot → {folder}")
    return 0


def _history(into: Path) -> int:
    from .history import history
    if not into.is_dir():
        print(f"weaver: no such folder: {into}", file=sys.stderr)
        return 2
    report = history(into)
    for name, why in report.skipped:
        print(f"weaver: skipped {name}: {why}", file=sys.stderr)
    if not report.read:
        print(f"weaver: no readable snapshot in {into}", file=sys.stderr)
        return 2
    for early in report.early:
        print(f"weaver: {early.node} first seen {early.status} in {early.snapshot}")
    n, s, e = len(report.read), len(report.skipped), len(report.early)
    counts = f"{n} snapshot{'s' * (n != 1)} read" + (f", {s} skipped" if s else "")
    verdict = (f"{e} node{'s' * (e != 1)} built or started before {'they were' if e != 1 else 'it was'} planned"
               if e else "every node was planned before work started")
    print(f"weaver: {counts}; {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
