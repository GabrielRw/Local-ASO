"""Local AI provider registry: Claude, Codex, Gemini, OpenCode, Ollama (all mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from local_aso_tracker.config import update_settings
from local_aso_tracker.services import agent

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
}


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))


def _installed(*names: str):  # type: ignore[no-untyped-def]
    return lambda provider, _configured="": f"/bin/{provider}" if provider in names else None


def test_registry_lists_every_provider_in_auto_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "_resolve_provider_executable", _installed("gemini"))
    statuses = agent.provider_status()
    assert [item.id for item in statuses] == ["claude", "codex", "gemini", "opencode", "ollama"]
    assert {item.id: item.available for item in statuses}["gemini"] is True
    assert agent._select_provider("auto") == "gemini"


def test_auto_prefers_claude_then_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent, "_resolve_provider_executable", _installed("codex", "claude", "gemini")
    )
    assert agent._select_provider("auto") == "claude"


def test_unknown_or_missing_providers_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "_resolve_provider_executable", _installed())
    with pytest.raises(ValueError):
        agent.validate_provider_id("openrouter")
    with pytest.raises(agent.AgentError, match="opencode CLI is not installed"):
        agent._select_provider("opencode")
    with pytest.raises(agent.AgentError, match="No local AI provider"):
        agent._select_provider("auto")


def test_saved_cli_paths_reach_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    update_settings(agent_gemini_path="/opt/tools/gemini")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        agent,
        "_resolve_provider_executable",
        lambda provider, configured="": configured or None,
    )

    def fake_gemini(
        prompt: str, timeout: float, *, schema: dict[str, Any], executable: str | None
    ) -> dict[str, Any]:
        seen["executable"] = executable
        return {"keywords": ["couples app"]}

    monkeypatch.setattr(agent, "_run_gemini", fake_gemini)
    # Niche keyword generation now goes through the shared runner, so saved paths apply.
    result = agent.generate_keywords(brief="apps for couples", provider="gemini")
    assert result.provider == "gemini"
    assert result.keywords == ["couples app"]
    assert seen["executable"] == "/opt/tools/gemini"


def _completed(stdout: str) -> agent.subprocess.CompletedProcess[str]:
    return agent.subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_gemini_runner_states_the_schema_and_unwraps_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], _timeout: float) -> agent.subprocess.CompletedProcess[str]:
        commands.append(command)
        return _completed(json.dumps({"response": '{"keywords": ["telepathy"]}', "stats": {}}))

    monkeypatch.setattr(agent, "_run", fake_run)
    raw = agent._run_gemini("Find keywords", 30, schema=SCHEMA, executable="/bin/gemini")
    assert raw == {"keywords": ["telepathy"]}
    command = commands[0]
    assert command[:2] == ["/bin/gemini", "-p"]
    assert command[-2:] == ["--output-format", "json"]
    assert '"required":["keywords"]' in command[2]


def test_opencode_runner_parses_json_from_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent,
        "_run",
        lambda command, _timeout: _completed('Here you go:\n{"keywords": ["soulmate"]}\n'),
    )
    assert agent._run_opencode("p", 30, schema=SCHEMA, executable="/bin/opencode") == {
        "keywords": ["soulmate"]
    }


def test_cli_output_that_is_not_json_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "_run", lambda command, _timeout: _completed("no json here"))
    with pytest.raises(agent.AgentError):
        agent._run_opencode("p", 30, schema=SCHEMA, executable="/bin/opencode")


def test_ollama_only_accepts_loopback_urls() -> None:
    assert agent.validate_ollama_url("http://localhost:11434/") == "http://localhost:11434"
    for url in ("http://192.168.1.10:11434", "https://ollama.example.com", "ftp://127.0.0.1"):
        with pytest.raises(ValueError):
            agent.validate_ollama_url(url)


def test_ollama_runner_sends_the_schema_as_format(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(config, method, path, *, timeout, payload=None):  # type: ignore[no-untyped-def]
        requests.append((method, path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:7b"}]}
        return {"message": {"content": '{"keywords": ["twin flame"]}'}}

    monkeypatch.setattr(agent, "_ollama_request", fake_request)
    update_settings(ollama_model="qwen2.5:7b")
    assert {item.id: item.available for item in agent.provider_status()}["ollama"] is True
    selected, raw = agent._run_structured_agent(
        "p", schema=SCHEMA, provider="ollama", codex_path="", claude_path="", timeout=30
    )
    assert selected == "ollama"
    assert raw == {"keywords": ["twin flame"]}
    chat = next(payload for method, path, payload in requests if path == "/api/chat")
    assert chat is not None
    assert chat["model"] == "qwen2.5:7b"
    assert chat["format"] == SCHEMA
    assert chat["stream"] is False


def test_ollama_without_models_is_unavailable() -> None:
    # The autouse fixture makes every Ollama request fail, as when it isn't running.
    assert {item.id: item.available for item in agent.provider_status()}["ollama"] is False
    with pytest.raises(agent.AgentError, match="Ollama is not running"):
        agent._select_provider("ollama")


def test_settings_reject_unknown_providers() -> None:
    with pytest.raises(ValueError):
        update_settings(agent_provider="openrouter")
