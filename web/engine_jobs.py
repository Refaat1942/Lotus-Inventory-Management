"""Background inventory engine jobs (avoids HTTP timeout on large datasets)."""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from config import DATA_DIR

JOBS_DIR = DATA_DIR / "engine_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _cleanup_old_jobs(max_age_sec: int = 7200) -> None:
    now = time.time()
    with _lock:
        stale = [jid for jid, meta in _jobs.items() if now - meta.get("created", now) > max_age_sec]
    for jid in stale:
        with _lock:
            _jobs.pop(jid, None)
        job_dir = JOBS_DIR / jid
        if job_dir.is_dir():
            for p in job_dir.iterdir():
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                job_dir.rmdir()
            except OSError:
                pass


def create_job() -> tuple[str, Path]:
    """Reserve a job id and folder; caller saves uploads then launches."""
    _cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        _jobs[job_id] = {
            "status": "queued",
            "progress": 0.0,
            "message": "Waiting for uploads",
            "error": None,
            "created": time.time(),
        }
    return job_id, job_dir


def launch_job(job_id: str, worker: Callable[[Callable], bytes]) -> None:
    def progress(val: float, text: str) -> None:
        with _lock:
            if job_id in _jobs:
                _jobs[job_id]["progress"] = float(val)
                _jobs[job_id]["message"] = str(text)

    def run() -> None:
        with _lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "running"
                _jobs[job_id]["message"] = "Processing..."
        job_dir = JOBS_DIR / job_id
        try:
            result = worker(progress)
            if not result:
                raise RuntimeError("Engine returned empty output")
            out_path = job_dir / "result.xlsx"
            out_path.write_bytes(result)
            with _lock:
                _jobs[job_id].update(
                    status="done",
                    progress=1.0,
                    message="Complete — click Download Excel Result",
                    error=None,
                    size=len(result),
                )
        except Exception as exc:
            with _lock:
                _jobs[job_id].update(
                    status="failed",
                    progress=0.0,
                    message=str(exc),
                    error=str(exc),
                )

    threading.Thread(target=run, daemon=True).start()


def start_job(worker: Callable[[Callable], bytes]) -> str:
    """Create job and launch worker (legacy helper)."""
    job_id, _ = create_job()
    launch_job(job_id, worker)
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        meta = _jobs.get(job_id)
        return dict(meta) if meta else None


def get_job_file(job_id: str) -> Optional[Path]:
    path = JOBS_DIR / job_id / "result.xlsx"
    return path if path.is_file() else None
