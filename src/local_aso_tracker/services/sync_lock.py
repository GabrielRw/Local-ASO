"""One rank sync at a time across processes (dashboard, CLI, background LaunchAgent)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from local_aso_tracker.config import data_dir

try:  # POSIX only; on other systems the lock is a no-op.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


class SyncBusy(RuntimeError):
    """Another process is already checking ranks."""


@contextmanager
def sync_lock() -> Iterator[None]:
    """Hold an exclusive, non-blocking lock on ``<data dir>/sync.lock``.

    Without it an open dashboard and a scheduled run could search Apple for the same
    keywords at the same moment and store duplicate checks. The OS releases the lock if
    the holder crashes, so a stale lock file never blocks later runs.
    """

    path = data_dir() / "sync.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle: IO[str] = path.open("a+", encoding="utf-8")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SyncBusy("another rank check is already running") from exc
        yield
    finally:
        handle.close()
