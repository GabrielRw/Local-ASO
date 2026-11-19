"""Background rank checks: the cross-process lock, `aso sync`, and the LaunchAgent."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_aso_tracker.cli import app
from local_aso_tracker.services import automatic_sync, background_sync
from local_aso_tracker.services.sync_lock import SyncBusy, sync_lock


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


def test_only_one_process_checks_ranks_at_a_time(tmp_path: Path) -> None:
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; from local_aso_tracker.services.sync_lock import sync_lock\n"
            "with sync_lock():\n    print('held', flush=True); time.sleep(5)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        with pytest.raises(SyncBusy), sync_lock():
            pass
        summary = automatic_sync.sync_all_current_keywords()
        assert summary.busy is True and summary.searches == 0
    finally:
        holder.kill()
        holder.wait()
    # Released when the holder exits, even without cleanup.
    with sync_lock():
        pass


def test_aso_sync_runs_migrations_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(
        "local_aso_tracker.cli.sync_all_current_keywords",
        lambda: (
            called.append(True)
            or automatic_sync.AutomaticSyncSummary(targets=2, searches=2, failures=0, skipped=3)
        ),
    )
    result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 0, result.output
    assert called == [True]
    assert "Checked 2 target(s)" in result.output


def test_aso_sync_fails_only_when_every_search_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "local_aso_tracker.cli.sync_all_current_keywords",
        lambda: automatic_sync.AutomaticSyncSummary(targets=2, searches=2, failures=2),
    )
    assert CliRunner().invoke(app, ["sync"]).exit_code == 1


@pytest.fixture
def launchctl(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def fake(*args: str) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(background_sync, "_launchctl", fake)
    monkeypatch.setattr(background_sync.sys, "platform", "darwin")
    return calls


def test_enable_writes_a_daily_agent_for_a_source_checkout(
    launchctl: list[tuple[str, ...]], isolated: Path
) -> None:
    status = background_sync.enable()
    plist = plistlib.loads(background_sync.plist_path().read_bytes())
    assert plist["Label"] == "app.localaso.sync"
    assert plist["ProgramArguments"] == [
        sys.executable,
        "-m",
        "local_aso_tracker",
        "--quiet",
        "sync",
    ]
    assert plist["RunAtLoad"] is True and plist["StartInterval"] == 86_400
    assert plist["EnvironmentVariables"]["ASO_DATA_DIR"] == str((isolated / "data").resolve())
    assert status["enabled"] is True and status["programMissing"] is False
    assert launchctl[-1][0] == "bootstrap"


def test_the_mac_app_schedules_its_bundled_server(
    launchctl: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    binary = isolated / "Local ASO.app" / "Contents" / "Resources" / "aso-server" / "aso-server"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    monkeypatch.setattr(background_sync.sys, "frozen", True, raising=False)
    monkeypatch.setattr(background_sync.sys, "executable", str(binary))
    background_sync.enable()
    plist = plistlib.loads(background_sync.plist_path().read_bytes())
    assert plist["ProgramArguments"] == [str(binary), "--quiet", "sync"]


def test_disable_unloads_and_removes_the_agent(launchctl: list[tuple[str, ...]]) -> None:
    background_sync.enable()
    status = background_sync.disable()
    assert status["enabled"] is False
    assert not background_sync.plist_path().exists()
    assert launchctl[-1][0] == "bootout"


def test_other_platforms_get_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(background_sync.sys, "platform", "linux")
    with pytest.raises(ValueError, match="cron or Task Scheduler"):
        background_sync.enable()
