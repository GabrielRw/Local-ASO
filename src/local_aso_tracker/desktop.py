"""Settings the Mac app's shell reads before the dashboard starts (``desktop.json``).

The Tauri shell can't query the server before launching it, so the few shell options
live in one small JSON file in the data folder, written only by the server.
"""

from __future__ import annotations

import json
from pathlib import Path

from local_aso_tracker.config import data_dir

DEFAULTS: dict[str, bool] = {"checkUpdates": True}


def desktop_settings_path() -> Path:
    return data_dir() / "desktop.json"


def load_desktop_settings() -> dict[str, bool]:
    try:
        stored = json.loads(desktop_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return {key: bool(stored.get(key, default)) for key, default in DEFAULTS.items()}


def save_desktop_settings(changes: dict[str, object]) -> dict[str, bool]:
    settings = load_desktop_settings()
    for key in DEFAULTS:
        if key in changes:
            settings[key] = bool(changes[key])
    path = desktop_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return settings
