"""Key-free first-run initialization and setup persistence."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from local_aso_tracker.apple.listing import AppleListing
from local_aso_tracker.cli import app
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import App, DashboardOnboarding, Storefront
from local_aso_tracker.web.server import DashboardService


@pytest.fixture
def fresh_dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DashboardService:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    service = DashboardService()
    monkeypatch.setattr(
        service,
        "listing",
        lambda app_id, country: AppleListing.model_validate(
            {"trackId": app_id, "trackName": "Test app", "bundleId": "example.test"}
        ),
    )
    return service


def test_first_run_remembers_dismissal_across_sessions(
    fresh_dashboard: DashboardService,
) -> None:
    assert fresh_dashboard.bootstrap(None, None)["onboarding"] == {
        "completed": False,
        "shouldOpen": True,
    }
    fresh_dashboard.finish_onboarding({})
    with session_scope() as session:
        first_completion = session.get(DashboardOnboarding, 1)
        assert first_completion is not None
        completed_at = first_completion.completed_at
    fresh_dashboard.finish_onboarding({})
    run_migrations()
    assert DashboardService().bootstrap(None, None)["onboarding"] == {
        "completed": True,
        "shouldOpen": False,
    }
    with session_scope() as session:
        completion = session.get(DashboardOnboarding, 1)
        assert completion is not None
        assert completion.completed_at == completed_at


def test_existing_workspace_does_not_interrupt_dashboard(
    fresh_dashboard: DashboardService,
) -> None:
    with session_scope() as session:
        session.add(App(name="Test app", apple_app_id=123456789))
    payload = fresh_dashboard.bootstrap(None, None)
    assert payload["onboarding"] == {"completed": False, "shouldOpen": False}
    assert "appleAds" not in payload


def test_legacy_credentials_are_not_read_or_returned(
    fresh_dashboard: DashboardService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from local_aso_tracker.config import data_dir

    legacy_file = data_dir() / "apple-ads.toml"
    legacy_file.write_text("invalid TOML private.jwt.token", encoding="utf-8")
    original_read = Path.open

    def guard_read(path: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if path == legacy_file:
            pytest.fail("retired credentials must not be read")
        return original_read(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", guard_read)
    payload = fresh_dashboard.bootstrap(None, None)
    assert payload["onboarding"] == {"completed": False, "shouldOpen": True}
    assert "private.jwt.token" not in json.dumps(payload)
    assert "appleAds" not in payload


def test_dashboard_launch_initializes_a_clean_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    calls: list[dict[str, object]] = []

    def serve(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("local_aso_tracker.web.server.serve_dashboard", serve)
    runner = CliRunner()
    for _ in range(2):
        result = runner.invoke(app, ["dashboard", "--no-open", "--port", "8766"])
        assert result.exit_code == 0, result.output
    assert len(calls) == 2
    assert (tmp_path / "config.toml").is_file()
    with session_scope() as session:
        assert session.scalars(select(App)).all() == []
        assert len(session.scalars(select(Storefront)).all()) == 5
    assert DashboardService().bootstrap(None, None)["onboarding"]["shouldOpen"] is True  # type: ignore[index]
