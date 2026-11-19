"""Behaviour the Tauri desktop shell relies on: free port, ready line, SIGTERM,
migrations shipped in the package, CLI discovery from a GUI launch, and recovery
of audits interrupted by quitting the app. Apple is never called."""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import inspect

from local_aso_tracker.database import (
    MIGRATIONS_DIR,
    create_db_engine,
    run_migrations,
    session_scope,
)
from local_aso_tracker.repositories.audits import (
    INTERRUPTED_MESSAGE,
    create_audit_run,
    get_audit_run,
    mark_interrupted_runs,
)
from local_aso_tracker.repositories.data import add_app, add_storefront
from local_aso_tracker.services import agent


def test_migrations_ship_inside_the_package(tmp_path: Path) -> None:
    assert MIGRATIONS_DIR.is_dir()
    assert MIGRATIONS_DIR.is_relative_to(Path(agent.__file__).resolve().parents[1])
    path = tmp_path / "aso.db"
    run_migrations(path)
    run_migrations(path)  # idempotent
    assert "keyword_popularity" in inspect(create_db_engine(path)).get_table_names()


def _start_dashboard(tmp_path: Path) -> subprocess.Popen[str]:
    env = {**os.environ, "ASO_DATA_DIR": str(tmp_path)}
    # Keep the background sync and MCP from touching the network during the test.
    code = (
        "import local_aso_tracker.web.server as s\n"
        "class Idle:\n"
        "    def start(self): return True\n"
        "    def stop(self, **_): pass\n"
        "    def status_payload(self): return {'state': 'idle'}\n"
        "s.AutomaticSyncWorker = Idle\n"
        "from local_aso_tracker.database import run_migrations\n"
        "run_migrations()\n"
        "s.serve_dashboard(port=0, mcp_enabled=False, open_browser=False)\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _ready_url(process: subprocess.Popen[str], timeout: float = 20) -> str:
    assert process.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line.startswith("LOCAL_ASO_READY "):
            return line.split(" ", 1)[1].strip()
        if not line and process.poll() is not None:
            break
    raise AssertionError("the dashboard never printed its ready line")


def test_port_zero_prints_ready_line_and_sigterm_stops_cleanly(tmp_path: Path) -> None:
    import httpx

    process = _start_dashboard(tmp_path)
    try:
        url = _ready_url(process)
        assert url.startswith("http://127.0.0.1:") and url.endswith("/")
        port = int(url.rstrip("/").rsplit(":", 1)[1])
        assert port not in (0, 8765)
        response = httpx.get(f"{url}api/sync-status", timeout=5, trust_env=False)
        assert response.status_code == 200
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=15) == 0
        assert process.stdout is not None
        assert "Dashboard stopped." in process.stdout.read()
    finally:
        if process.poll() is None:
            process.kill()


def test_cli_discovery_looks_beyond_a_gui_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\necho 1.0\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.setattr(agent, "_LOGIN_SHELL_PATH", [])

    assert agent._resolve_provider_executable("claude") == str(fake)
    statuses = {item.id: item.available for item in agent.provider_status()}
    assert statuses["claude"] is True


def test_audits_left_running_are_marked_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Example", 123456789)
        add_storefront(session, "us", "United States")
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="claude",
            country_codes=["us"],
        )
        run.status = "running"
        session.flush()
        run_id = run.id

    with session_scope() as session:
        assert mark_interrupted_runs(session) == 1
    with session_scope() as session:
        stored = get_audit_run(session, run_id)
        assert stored is not None
        assert stored.status == "error"
        assert stored.error_message == INTERRUPTED_MESSAGE
        assert all(country.status == "error" for country in stored.countries)
        assert mark_interrupted_runs(session) == 0
