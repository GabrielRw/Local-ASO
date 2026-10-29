"""Background startup and daily keyword synchronization."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from local_aso_tracker.config import Settings, load_settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import TrackingTarget
from local_aso_tracker.repositories.data import filter_targets_due_for_check, list_targets
from local_aso_tracker.services.checks import CheckRunResult, run_checks

logger = logging.getLogger(__name__)
SECONDS_PER_DAY = 24 * 60 * 60
SyncState = Literal["idle", "running", "success", "partial", "error"]
CheckRunner = Callable[[Session, list[TrackingTarget], Settings], CheckRunResult]


@dataclass(frozen=True)
class AutomaticSyncSummary:
    """One completed synchronization attempt."""

    targets: int
    searches: int
    failures: int
    skipped: int = 0


def sync_all_current_keywords(
    *,
    check_runner: CheckRunner | None = None,
) -> AutomaticSyncSummary:
    """Check every active target across every active app, market, and device."""

    settings = load_settings()
    runner = check_runner or run_checks
    with session_scope() as session:
        targets = list_targets(session, active_only=True)
        if not targets:
            return AutomaticSyncSummary(targets=0, searches=0, failures=0)
        due_targets, skipped = filter_targets_due_for_check(
            session,
            targets,
            cutoff=datetime.now(UTC) - timedelta(hours=24),
        )
        if not due_targets:
            return AutomaticSyncSummary(targets=0, searches=0, failures=0, skipped=skipped)
        result = runner(session, due_targets, settings)
    return AutomaticSyncSummary(
        targets=len(due_targets),
        searches=result.searches,
        failures=result.failures,
        skipped=skipped,
    )


class AutomaticSyncWorker:
    """Run synchronization immediately, then once per interval while the app is open."""

    def __init__(
        self,
        *,
        interval_seconds: float = SECONDS_PER_DAY,
        sync_runner: Callable[[], AutomaticSyncSummary] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("sync interval must be positive")
        self.interval = timedelta(seconds=interval_seconds)
        self._sync_runner = sync_runner or sync_all_current_keywords
        self._state: SyncState = "idle"
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._next_run_at: datetime | None = None
        self._targets = 0
        self._searches = 0
        self._failures = 0
        self._skipped = 0
        self._error: str | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Start the background thread once."""

        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="local-aso-automatic-sync",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, *, timeout: float = 3.0) -> None:
        """Ask the worker to stop waiting or exit after its current check finishes."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-safe snapshot for the local dashboard."""

        with self._lock:
            return {
                "state": self._state,
                "startedAt": _iso(self._started_at),
                "finishedAt": _iso(self._finished_at),
                "nextRunAt": _iso(self._next_run_at),
                "targets": self._targets,
                "searches": self._searches,
                "failures": self._failures,
                "skipped": self._skipped,
                "error": self._error,
            }

    def _run_loop(self) -> None:
        deadline = datetime.now(UTC)
        while not self._stop.is_set():
            self._run_once()
            deadline += self.interval
            wait_seconds = max(0.0, (deadline - datetime.now(UTC)).total_seconds())
            with self._lock:
                self._next_run_at = deadline
            if self._stop.wait(wait_seconds):
                break

    def _run_once(self) -> None:
        started_at = datetime.now(UTC)
        with self._lock:
            self._state = "running"
            self._started_at = started_at
            self._finished_at = None
            self._next_run_at = None
            self._targets = 0
            self._searches = 0
            self._failures = 0
            self._skipped = 0
            self._error = None
        try:
            summary = self._sync_runner()
        except Exception as exc:
            logger.exception("Automatic keyword synchronization failed")
            with self._lock:
                self._state = "error"
                self._finished_at = datetime.now(UTC)
                self._error = str(exc)[:400]
            return
        state: SyncState = "partial" if summary.failures else "success"
        with self._lock:
            self._state = state
            self._finished_at = datetime.now(UTC)
            self._targets = summary.targets
            self._searches = summary.searches
            self._failures = summary.failures
            self._skipped = summary.skipped
        logger.info(
            "Automatic keyword sync complete: targets=%s searches=%s failures=%s skipped=%s",
            summary.targets,
            summary.searches,
            summary.failures,
            summary.skipped,
        )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
