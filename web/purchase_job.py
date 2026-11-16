"""Purchase engine run executed in its own process by engine_jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from engine import parse_blocked_df, parse_rank_df, process_inventory
from excel_io import read_excel_path


def load_engine_inputs_from_dir(job_dir: Path) -> dict:
    main_df = read_excel_path(job_dir / "main.xlsx")
    if main_df is None:
        raise ValueError("Main ERP Sheet missing or invalid")

    targets_df = read_excel_path(job_dir / "targets.xlsx")
    avoid_zero_df = read_excel_path(job_dir / "avoid_zero.xlsx")
    rank_df = read_excel_path(job_dir / "rank.xlsx")
    rank_data = parse_rank_df(rank_df) if rank_df is not None else {}

    purchase_targets_df = read_excel_path(job_dir / "purchase_targets.xlsx")
    similar_df = read_excel_path(job_dir / "similar.xlsx")

    blocked_items, blocked_branches = set(), set()
    blocked_df = read_excel_path(job_dir / "blocked.xlsx")
    if blocked_df is not None:
        blocked_items, blocked_branches = parse_blocked_df(blocked_df)

    blocked_os_items, blocked_os_branches = set(), set()
    blocked_os_df = read_excel_path(job_dir / "blocked_os.xlsx")
    if blocked_os_df is not None:
        blocked_os_items, blocked_os_branches = parse_blocked_df(blocked_os_df)

    return {
        "main_df": main_df,
        "targets_df": targets_df,
        "purchase_targets_df": purchase_targets_df,
        "rank_data": rank_data,
        "avoid_zero_df": avoid_zero_df,
        "similar_df": similar_df,
        "blocked_items": blocked_items,
        "blocked_branches": blocked_branches,
        "blocked_os_items": blocked_os_items,
        "blocked_os_branches": blocked_os_branches,
    }


def run_purchase_job(
    progress: Callable[[float, str], None],
    job_dir: str,
    zero_overstock: bool,
    sto_threshold: int,
) -> bytes:
    progress(0.02, "Reading uploaded Excel files...")
    inputs = load_engine_inputs_from_dir(Path(job_dir))
    progress(0.05, "Running inventory engine...")
    return process_inventory(
        **inputs,
        zero_overstock=zero_overstock,
        sto_threshold=sto_threshold,
        progress_callback=progress,
    )
