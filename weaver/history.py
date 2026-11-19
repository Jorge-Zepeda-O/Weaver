"""A4-5: snapshots of a plan, and what their history shows was built before it was planned.

A snapshot is a folder ``PLAN_<YYYYMMDD_HHMMSS>/`` holding the plan file byte for byte
(``plan.toml``) and its page and Markdown views. Read in time order, a series of them is
an audit trail: a node whose first appearance is already done or doing was built or
started before it was planned. The first snapshot is no baseline; work already in it has
no plan on record either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .load import PlanError, load_plan

SNAPSHOT_NAME = re.compile(r"PLAN_[0-9]{8}_[0-9]{6}")
EARLY_STATUSES = ("done", "doing")


def snapshot(plan_path: Path, into: Path, now: datetime) -> Path:
    """Write ``into/PLAN_<now>/`` and return it. Raises ``PlanError`` for an invalid plan
    (writing nothing) and ``FileExistsError`` rather than overwrite a snapshot."""
    plan = load_plan(plan_path)
    from .dot import render_svg
    from .html import build_html
    from .markdown import to_markdown

    folder = into / f"PLAN_{now:%Y%m%d_%H%M%S}"
    svg = render_svg(plan)
    views = {"PLAN.html": build_html(plan, svg), "PLAN.md": to_markdown(plan)}
    folder.mkdir(parents=True)  # FileExistsError if this second already has a snapshot
    (folder / "plan.toml").write_bytes(Path(plan_path).read_bytes())
    for name, text in views.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


@dataclass(frozen=True)
class Early:
    """``node`` first appeared in ``snapshot`` with status ``status`` (done or doing)."""
    node: str
    status: str
    snapshot: str


@dataclass(frozen=True)
class History:
    read: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (snapshot, why)
    early: tuple[Early, ...]


def history(into: Path) -> History:
    """Read every ``PLAN_<stamp>`` folder in ``into`` in time order; anything else is ignored."""
    read: list[str] = []
    skipped: list[tuple[str, str]] = []
    first_seen: dict[str, Early] = {}
    for folder in sorted(p for p in into.iterdir() if p.is_dir() and SNAPSHOT_NAME.fullmatch(p.name)):
        plan_file = folder / "plan.toml"
        if not plan_file.is_file():
            skipped.append((folder.name, "no plan.toml"))
            continue
        try:
            plan = load_plan(plan_file)
        except PlanError as exc:
            skipped.append((folder.name, f"invalid plan: {exc}".splitlines()[0]))
            continue
        read.append(folder.name)
        for node in plan.nodes:
            first_seen.setdefault(node.id, Early(node.id, node.status, folder.name))
    early = tuple(e for e in first_seen.values() if e.status in EARLY_STATUSES)
    return History(tuple(read), tuple(skipped), early)
