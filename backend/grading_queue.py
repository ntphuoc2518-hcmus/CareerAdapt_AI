"""Grade submitted exams outside the request (audit B-04).

Submitting only locks the answers (IN_PROGRESS -> SUBMITTED) and puts the attempt on this queue, so the
request returns at once however long the code runs. A small, fixed pool of worker threads grades, which
caps how many sandboxes run at the same time. The attempt's own status is the source of truth: a job
lost to a restart is found again by ``recover`` (called on start and on every background tick), and the
atomic SUBMITTED -> GRADING claim in each grader means a job can never be graded twice.

Under pytest the queue runs jobs inline by default, so existing tests keep their synchronous view;
``use_background`` switches a test to the real background path.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

logger = logging.getLogger("careeradapt.grading")

WORKERS = max(1, int(os.getenv("CAREERADAPT_GRADING_WORKERS", "2")))
# Longest a grading job may run before another process treats it as lost and grades it again.
LEASE_SECONDS = float(os.getenv("CAREERADAPT_GRADING_LEASE", "600"))
_lock = threading.Lock()
_active: dict[str, Optional[Future]] = {}
_executor: Optional[ThreadPoolExecutor] = None
_background = "pytest" not in sys.modules and os.getenv("CAREERADAPT_SYNC_GRADING", "false").lower() != "true"


def use_background(enabled: bool) -> None:
    """Tests only: grade in worker threads (True) or inline (False)."""
    global _background
    _background = enabled


def background_enabled() -> bool:
    return _background


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="grading")
        return _executor


def is_active(key: str) -> bool:
    with _lock:
        return key in _active


def take_lease(key: str, seconds: float) -> Optional[str]:
    """Claim ``key`` for this process across every process; None when someone else holds a live lease."""
    from backend.store import PROCESS_ID, store

    owner = f"{PROCESS_ID}:{uuid.uuid4().hex[:8]}"
    now = time.time()
    with store.db.transaction():
        store.db.execute("DELETE FROM work_leases WHERE lease_key = ? AND expires_at < ?", (key, now))
        store.db.execute("INSERT OR IGNORE INTO work_leases(lease_key, owner, expires_at) VALUES (?, ?, ?)", (key, owner, now + seconds))
        row = store.db.one("SELECT owner FROM work_leases WHERE lease_key = ?", (key,))
    return owner if row and row["owner"] == owner else None


def drop_lease(key: str, owner: str) -> None:
    from backend.store import store

    store.db.execute("DELETE FROM work_leases WHERE lease_key = ? AND owner = ?", (key, owner))


def lease_alive(key: str) -> bool:
    from backend.store import store

    return store.db.one("SELECT 1 AS alive FROM work_leases WHERE lease_key = ? AND expires_at >= ?", (key, time.time())) is not None


def enqueue(key: str, job: Callable[[], None]) -> bool:
    """Schedule ``job`` once per key. Returns False when that key is already queued or running.

    Inline mode runs the job now and lets its error reach the caller, as grading did before.
    """
    with _lock:
        if key in _active:
            return False
        _active[key] = None
    lease = take_lease(f"grading:{key}", LEASE_SECONDS)
    if lease is None:
        # Another server process is grading it right now.
        with _lock:
            _active.pop(key, None)
        return False
    if not _background:
        try:
            job()
        finally:
            drop_lease(f"grading:{key}", lease)
            with _lock:
                _active.pop(key, None)
        return True

    def run() -> None:
        try:
            job()
        except Exception:
            # The attempt went back to SUBMITTED; the next tick or read queues it again. No answer text is logged.
            logger.exception("Grading job %s failed; it will be retried", key)
        finally:
            drop_lease(f"grading:{key}", lease)
            with _lock:
                _active.pop(key, None)

    future = _pool().submit(run)
    with _lock:
        if key in _active:
            _active[key] = future
    return True


def wait_idle(timeout: float = 60.0) -> bool:
    """Tests and shutdown: wait until every queued job has finished."""
    with _lock:
        futures = [future for future in _active.values() if future is not None]
    for future in futures:
        try:
            future.result(timeout=timeout)
        except Exception:
            return False
    return True


def recover() -> int:
    """Queue every attempt that is waiting to be graded, including GRADING rows no worker owns (lost to a restart)."""
    from backend import exam_service, final_assessment

    return exam_service.queue_pending() + final_assessment.queue_pending()
