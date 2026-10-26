"""Background full-catalog synchronization tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import seed_catalog, seed_targets
from local_aso_tracker.services import automatic_sync


@pytest.fixture
def sync_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)


def test_sync_all_current_keywords_checks_every_active_target(
    sync_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[int] = []

    def fake_run_checks(session, targets, settings):  # type: ignore[no-untyped-def]
        checked.extend(target.id for target in targets)
        return SimpleNamespace(checks=[], searches=len(targets), failures=0)

    result = automatic_sync.sync_all_current_keywords(check_runner=fake_run_checks)

    assert result.targets == 75
    assert len(checked) == 75
    assert result.searches == 75
    assert result.failures == 0


def test_automatic_sync_worker_runs_immediately_and_reports_status() -> None:
    completed = automatic_sync.threading.Event()
    worker = automatic_sync.AutomaticSyncWorker(
        interval_seconds=3600,
        sync_runner=lambda: _complete_sync(completed),
    )

    assert worker.start() is True
    assert completed.wait(timeout=2)
    worker.stop()

    status = worker.status_payload()
    assert status["state"] == "success"
    assert status["targets"] == 75
    assert status["searches"] == 6
    assert status["finishedAt"] is not None
    assert status["nextRunAt"] is not None


def test_automatic_sync_worker_captures_errors() -> None:
    completed = automatic_sync.threading.Event()

    def fail() -> automatic_sync.AutomaticSyncSummary:
        completed.set()
        raise RuntimeError("Apple unavailable")

    worker = automatic_sync.AutomaticSyncWorker(interval_seconds=3600, sync_runner=fail)
    worker.start()
    assert completed.wait(timeout=2)
    worker.stop()

    status = worker.status_payload()
    assert status["state"] == "error"
    assert status["error"] == "Apple unavailable"


def _complete_sync(
    completed: automatic_sync.threading.Event,
) -> automatic_sync.AutomaticSyncSummary:
    completed.set()
    return automatic_sync.AutomaticSyncSummary(targets=75, searches=6, failures=0)
