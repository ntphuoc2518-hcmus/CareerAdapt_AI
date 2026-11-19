"""A lock file shared by every process on this machine (5.34).

Used around database start-up: creating tables, switching to WAL and running migrations. When several
server processes start together on a new or older database, they take turns here instead of racing on
the same schema change (which SQLite reports as "database is locked" or "duplicate column").
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive(path: str | Path, timeout: float = 120.0) -> Iterator[None]:
    """Hold ``<path>.startup.lock`` exclusively. In-memory databases (":memory:") need no lock."""
    if str(path) == ":memory:":
        yield
        return
    lock_path = Path(f"{path}.startup.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"start-up lock {lock_path} is still held")
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
