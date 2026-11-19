"""Opt-in daily rank checks while Local ASO is closed (macOS LaunchAgent).

The agent runs `aso --quiet sync` once at login and then every 24 hours: from the Mac
app it runs the bundled server binary, from a source checkout it runs this Python. It
uses the same data folder as the app, and the shared sync lock keeps it from running
alongside an open dashboard's own sync.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_aso_tracker.config import data_dir, log_path

LABEL = "app.localaso.sync"
INTERVAL_SECONDS = 24 * 60 * 60


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def plist_path() -> Path:
    return _home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def sync_log_path() -> Path:
    return log_path().parent / "background-sync.log"


def program_arguments() -> list[str]:
    """The command launchd runs: the frozen app binary, or this interpreter for a checkout."""

    if getattr(sys, "frozen", False):
        return [sys.executable, "--quiet", "sync"]
    return [sys.executable, "-m", "local_aso_tracker", "--quiet", "sync"]


def build_plist() -> dict[str, Any]:
    log = str(sync_log_path())
    return {
        "Label": LABEL,
        "ProgramArguments": program_arguments(),
        "EnvironmentVariables": {"ASO_DATA_DIR": str(data_dir())},
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise ValueError(
            "Background checks are available on macOS. On Linux or Windows, schedule "
            "`aso sync` with cron or Task Scheduler."
        )


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def status() -> dict[str, object]:
    """Whether the agent is installed, what it runs, and when it last wrote its log."""

    path = plist_path()
    installed = path.is_file()
    program: list[str] | None = None
    if installed:
        try:
            with path.open("rb") as handle:
                program = list(plistlib.load(handle).get("ProgramArguments") or [])
        except (OSError, plistlib.InvalidFileException):
            program = None
    log = sync_log_path()
    last_run = (
        datetime.fromtimestamp(log.stat().st_mtime, tz=UTC).isoformat() if log.is_file() else None
    )
    return {
        "supported": sys.platform == "darwin",
        "enabled": installed,
        "plistPath": str(path),
        "program": program,
        # A moved or replaced app leaves the agent pointing at a missing binary.
        "programMissing": bool(program) and not Path(program[0]).exists(),  # type: ignore[index]
        "lastRunAt": last_run,
        "logPath": str(log),
    }


def enable() -> dict[str, object]:
    """Write the LaunchAgent and load it (replacing an older copy)."""

    _require_macos()
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sync_log_path().parent.mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    with path.open("wb") as handle:
        plistlib.dump(build_plist(), handle)
    loaded = _launchctl("bootstrap", _domain(), str(path))
    if loaded.returncode != 0:
        detail = " ".join((loaded.stderr or loaded.stdout).split())[:200]
        raise ValueError(f"launchctl could not load the background check: {detail}")
    return status()


def disable() -> dict[str, object]:
    """Unload and delete the LaunchAgent; harmless when it isn't installed."""

    _require_macos()
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    plist_path().unlink(missing_ok=True)
    return status()
