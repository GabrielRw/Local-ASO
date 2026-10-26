"""Local agent adapter parsing tests without invoking a model."""

import pytest

from local_aso_tracker.services import agent


def test_agent_keywords_are_normalized_deduplicated_and_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "_select_provider", lambda _provider: "codex")
    monkeypatch.setattr(
        agent,
        "_run_codex",
        lambda _prompt, _timeout: {
            "keywords": [
                "  keto   tracker ",
                "Keto Tracker",
                "keto diet",
                "keto snacks",
                "keto app",
            ]
        },
    )

    result = agent.generate_keywords(
        brief="keto tracking",
        existing_keywords=["keto app"],
        count=3,
        provider="auto",
    )

    assert result.provider == "codex"
    assert result.keywords == ["keto tracker", "keto diet", "keto snacks"]


def test_agent_requires_a_keyword_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "_select_provider", lambda _provider: "codex")
    monkeypatch.setattr(agent, "_run_codex", lambda _prompt, _timeout: {"items": []})

    with pytest.raises(agent.AgentError):
        agent.generate_keywords(brief="keto tracking", provider="auto")


def test_claude_result_can_be_an_embedded_json_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent, "shutil", type("Shutil", (), {"which": lambda _self, _name: "/bin/claude"})()
    )
    monkeypatch.setattr(
        agent,
        "_run",
        lambda _command, _timeout: agent.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"result": "{\\"keywords\\": [\\"keto tracker\\"]}"}',
            stderr="",
        ),
    )

    result = agent._run_claude("prompt", 10)

    assert result == {"keywords": ["keto tracker"]}
