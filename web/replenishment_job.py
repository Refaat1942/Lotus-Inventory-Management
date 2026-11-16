"""Replenishment engine run executed in its own process by engine_jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from excel_io import read_excel_path
from replenishment_engine import (
    apply_targets_excel,
    extract_branches,
    parse_blocked_df,
    parse_rank_df,
    process_replenishment,
)


def merge_uploaded_targets(targets: dict, main_df, targets_df) -> dict:
    """Apply the uploaded targets file server-side so a run never depends on the
    browser's branch boxes having been filled. Values typed in the UI win; a
    branch/category left at 0 takes the value from the file."""
    if targets_df is None:
        return targets
    merged = {k: dict(v) for k, v in (targets or {}).items()}
    from_file = apply_targets_excel(targets_df, extract_branches(main_df), main_df)
    for branch, vals in from_file.items():
        entry = merged.setdefault(branch, {"pharma": 0.0, "non_pharma": 0.0})
        for kind in ("pharma", "non_pharma"):
            try:
                current = float(entry.get(kind) or 0)
            except (TypeError, ValueError):
                current = 0.0
            if current <= 0 and vals.get(kind, 0) > 0:
                entry[kind] = vals[kind]
    return merged


def run_replenishment_job(
    progress: Callable[[float, str], None],
    job_dir: str,
    branch_targets: dict,
) -> bytes:
    d = Path(job_dir)
    progress(0.02, "Reading uploaded Excel files...")
    main_df = read_excel_path(d / "main.xlsx")
    if main_df is None:
        raise ValueError("Main Dataset missing or invalid")
    targets = merge_uploaded_targets(branch_targets, main_df, read_excel_path(d / "targets.xlsx"))
    rank_df = read_excel_path(d / "rank.xlsx")
    blocked_items, blocked_branches = set(), set()
    blocked_df = read_excel_path(d / "blocked.xlsx")
    if blocked_df is not None:
        blocked_items, blocked_branches = parse_blocked_df(blocked_df)
    return process_replenishment(
        main_df=main_df,
        branch_targets=targets,
        rank_data=parse_rank_df(rank_df) if rank_df is not None else {},
        blocked_items=blocked_items,
        blocked_branches=blocked_branches,
        similar_df=read_excel_path(d / "similar.xlsx"),
        progress_callback=progress,
    )
