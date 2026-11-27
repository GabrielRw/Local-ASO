"""How local AI CLIs are found, isolated, checked for sign-in, and fallen back from."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from local_aso_tracker.services import agent


def _script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def clean_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(agent, "_LOGIN_SHELL_PATH", [])
    monkeypatch.setattr(agent, "_EXTRA_BIN_DIRS", ("~/.local/bin", "~/brew/bin"))
    monkeypatch.setattr(agent, "_VERSION_CACHE", {})
    return tmp_path / "home"


def test_cli_runs_in_an_empty_folder_with_a_usable_path(clean_paths: Path) -> None:
    tool = _script(clean_paths / ".local/bin/claude", 'echo "$PWD"; echo "$PATH"; ls -A')
    completed = agent._run([str(tool)], 10)
    workdir, path, *listing = completed.stdout.splitlines()
    assert "local-aso-agent-" in workdir and listing == []  # nothing to pick up
    assert workdir != os.getcwd() and not Path(workdir).exists()  # cleaned up
    assert str(tool.parent) in path.split(os.pathsep)  # npm CLIs can find `node` beside them


def test_newest_copy_wins_and_every_copy_is_reported(clean_paths: Path) -> None:
    old = _script(clean_paths / ".local/bin/claude", "echo '2.1.29 (Claude Code)'")
    new = _script(clean_paths / "brew/bin/claude", "echo '2.1.30 (Claude Code)'")
    installs = agent.cli_installs("claude")
    assert [item.path for item in installs] == [str(new), str(old)]
    assert installs[0].version == "2.1.30 (Claude Code)"
    assert agent._find_cli("claude") == str(new)
    status = {item.id: item for item in agent.provider_status()}["claude"]
    assert status.path == str(new) and status.version == "2.1.30 (Claude Code)"
    assert len(status.installs) == 2


def test_a_chosen_copy_overrides_the_newest(clean_paths: Path) -> None:
    old = _script(clean_paths / ".local/bin/claude", "echo 2.1.29")
    _script(clean_paths / "brew/bin/claude", "echo 2.1.30")
    status = {item.id: item for item in agent.provider_status(paths={"claude": str(old)})}["claude"]
    assert status.path == str(old) and status.version == "2.1.29"


def test_claude_requests_ignore_project_settings_hooks_and_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '{"structured_output": {"ok": true}}', "")

    monkeypatch.setattr(agent, "_run", fake_run)
    agent._run_claude("prompt", 10, schema={"type": "object"}, executable="/bin/claude")
    command = commands[0]
    assert command[command.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in command
    assert command[command.index("--tools") + 1] == ""


def test_a_normal_answer_mentioning_login_is_not_a_sign_in_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = iter(
        [
            {"is_error": False, "result": "Sure. Type /login to re-authenticate."},
            {"is_error": True, "result": "Failed to authenticate. API Error: 401"},
            {"is_error": True, "result": "Rate limited, try later"},
        ]
    )
    monkeypatch.setattr(
        agent,
        "_run",
        lambda command, _timeout: subprocess.CompletedProcess(
            command, 0, json.dumps(next(answers)), ""
        ),
    )
    assert agent._claude_auth_problem("/bin/claude") is None
    assert agent._claude_auth_problem("/bin/claude") == agent.CLAUDE_SIGNED_OUT
    assert agent._claude_auth_problem("/bin/claude") is None


def test_a_cli_that_exits_with_a_login_error_says_so(
    clean_paths: Path,
) -> None:
    tool = _script(clean_paths / ".local/bin/codex", "echo 'Error: not logged in' >&2; exit 1")
    with pytest.raises(agent.AgentError, match="Codex CLI is signed out"):
        agent._run([str(tool), "exec"], 10)


def _providers(monkeypatch: pytest.MonkeyPatch, available: set[str]) -> None:
    monkeypatch.setattr(
        agent, "_provider_available", lambda provider, _config: provider in available
    )


def test_auto_falls_back_to_the_next_working_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _providers(monkeypatch, {"claude", "codex"})
    calls: list[str] = []

    def fake_provider(selected: str, *_args: object, **_kwargs: object) -> dict[str, Any]:
        calls.append(selected)
        if selected == "claude":
            raise agent.AgentError(agent.CLAUDE_SIGNED_OUT)
        return {"keywords": ["dream journal"]}

    monkeypatch.setattr(agent, "_run_provider", fake_provider)
    result = agent.generate_keywords(brief="dreams", provider="auto")
    assert calls == ["claude", "codex"]
    assert result.provider == "codex" and result.keywords == ["dream journal"]

    calls.clear()
    with pytest.raises(agent.AgentError, match="signed out"):
        agent.generate_keywords(brief="dreams", provider="claude")
    assert calls == ["claude"]  # an explicit choice never falls back


def test_when_every_provider_fails_the_errors_are_combined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _providers(monkeypatch, {"claude", "gemini"})

    def failing(selected: str, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise agent.AgentError(f"{selected} broke")

    monkeypatch.setattr(agent, "_run_provider", failing)
    with pytest.raises(agent.AgentError, match=r"claude broke \(also tried gemini: gemini broke\)"):
        agent.generate_keywords(brief="dreams", provider="auto")


def test_check_reports_signed_out_and_working(
    clean_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(clean_paths / ".local/bin/claude", "echo 2.1.30")
    monkeypatch.setattr(agent, "_claude_auth_problem", lambda _path: agent.CLAUDE_SIGNED_OUT)
    result = agent.check_provider("claude")
    assert result["signedIn"] is False and result["ok"] is False
    assert result["version"] == "2.1.30"

    monkeypatch.setattr(agent, "_claude_auth_problem", lambda _path: None)
    monkeypatch.setattr(agent, "_run_provider", lambda *_args, **_kwargs: {"ok": True})
    result = agent.check_provider("claude")
    assert result["ok"] is True and result["signedIn"] is True

    missing = agent.check_provider("gemini")
    assert missing["ok"] is False and "not installed" in str(missing["message"])


def test_sign_in_opens_terminal_with_the_quoted_command(
    clean_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _script(clean_paths / ".local/bin/codex", "echo 0.50")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "osascript":
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    result = agent.open_sign_in("codex")
    assert result["command"] == f"{tool} login"
    script = calls[0][2]
    assert script.startswith('tell application "Terminal" to do script "cd ~ && ')
    assert f"{tool} login" in script
    with pytest.raises(ValueError):
        agent.open_sign_in("ollama")
