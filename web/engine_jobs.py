"""Background engine jobs (avoids HTTP timeouts on large datasets).

Each job runs in its own child process, so a run that exhausts memory is the
one killed instead of the whole web server, and the server stays responsive
while it works. Job status lives in <job dir>/status.json, so it survives a
server restart and the page gets a clear message instead of "job not found".
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from config import DATA_DIR

JOBS_DIR = DATA_DIR / "engine_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Engine runs can each need GBs of RAM on large sheets; run them one at a time.
_MAX_PARALLEL = max(1, int(os.getenv("LOTUS_MAX_ENGINE_JOBS", "1")))
_slots = threading.Semaphore(_MAX_PARALLEL)
# Identifies this server process; jobs left "running" by an earlier one were cut off.
_INSTANCE = uuid.uuid4().hex
_lock = threading.Lock()
# "spawn" starts a clean interpreter: safe to use from the threaded web server.
_mp = multiprocessing.get_context("spawn")


def _status_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "status.json"


def _write_status(job_id: str, **fields) -> None:
    path = _status_path(job_id)
    with _lock:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        meta.update(fields)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp, path)


def _cleanup_old_jobs(max_age_sec: int = 7200) -> None:
    now = time.time()
    for job_dir in JOBS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        try:
            meta = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if meta.get("status") in ("queued", "running") and meta.get("instance") == _INSTANCE:
            continue  # still working in this server
        try:
            age = now - job_dir.stat().st_mtime
        except OSError:
            continue
        if age > max_age_sec:
            shutil.rmtree(job_dir, ignore_errors=True)


def create_job(kind: str = "purchase") -> tuple[str, Path]:
    """Reserve a job id and folder; caller saves uploads then launches."""
    _cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_status(
        job_id,
        status="queued",
        progress=0.0,
        message="Waiting for uploads",
        error=None,
        created=time.time(),
        instance=_INSTANCE,
        kind=kind,
    )
    return job_id, job_dir


def _child_main(job_id: str, target: Callable, kwargs: dict) -> None:
    """Runs inside the child process."""
    last = [0.0]

    def progress(val: float, text: str) -> None:
        now = time.time()
        if now - last[0] >= 0.5 or val >= 1.0:
            last[0] = now
            _write_status(job_id, progress=float(val), message=str(text))

    _write_status(job_id, status="running", message="Processing...")
    try:
        result = target(progress, **kwargs)
        if not result:
            raise RuntimeError("Engine returned empty output")
        (JOBS_DIR / job_id / "result.xlsx").write_bytes(result)
        _write_status(
            job_id,
            status="done",
            progress=1.0,
            message="Complete — click Download Excel Result",
            error=None,
            size=len(result),
        )
    except BaseException as exc:  # report every failure to the page
        msg = str(exc) or exc.__class__.__name__
        if isinstance(exc, MemoryError):
            msg = "Server ran out of memory on this dataset. Try splitting the ERP sheet."
        _write_status(job_id, status="failed", progress=0.0, message=msg, error=msg)
        raise


def launch_job(job_id: str, target: Callable, **kwargs) -> None:
    """Run target(progress, **kwargs) -> bytes in a child process.

    target must be a module-level function (it is imported by the child).
    """

    def supervise() -> None:
        if not _slots.acquire(blocking=False):
            _write_status(job_id, message="Waiting for another engine run to finish...")
            _slots.acquire()
        try:
            proc = _mp.Process(target=_child_main, args=(job_id, target, kwargs), daemon=True)
            proc.start()
            proc.join()
            meta = get_job(job_id) or {}
            if meta.get("status") not in ("done", "failed"):
                if proc.exitcode in (-9, 137):
                    msg = "The engine was stopped because the server ran out of memory. Try a smaller ERP sheet."
                elif proc.exitcode in (-15, 143):
                    msg = "The server restarted while this run was processing. Please run the engine again."
                else:
                    msg = f"The engine process stopped unexpectedly (exit code {proc.exitcode}). Run again."
                _write_status(job_id, status="failed", progress=0.0, message=msg, error=msg)
        except Exception as exc:
            _write_status(job_id, status="failed", progress=0.0, message=str(exc), error=str(exc))
        finally:
            _slots.release()

    threading.Thread(target=supervise, daemon=True).start()


def fail_job(job_id: str, message: str) -> None:
    """Mark a job that never launched (e.g. a rejected upload) as failed so it gets cleaned up."""
    _write_status(job_id, status="failed", progress=0.0, message=message, error=message)


def get_job(job_id: str, kind: Optional[str] = None) -> Optional[dict]:
    if not job_id or not all(c in "0123456789abcdef" for c in job_id):
        return None
    try:
        meta = json.loads(_status_path(job_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if kind is not None and meta.get("kind", "purchase") != kind:
        return None
    if meta.get("status") in ("queued", "running") and meta.get("instance") != _INSTANCE:
        msg = "The server restarted while this run was processing. Please run the engine again."
        _write_status(job_id, status="failed", progress=0.0, message=msg, error=msg)
        meta.update(status="failed", progress=0.0, message=msg, error=msg)
    return meta


def get_job_file(job_id: str, kind: Optional[str] = None) -> Optional[Path]:
    if get_job(job_id, kind) is None:
        return None
    path = JOBS_DIR / job_id / "result.xlsx"
    return path if path.is_file() else None
