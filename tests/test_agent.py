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


def test_audit_agent_keeps_only_requested_markets_and_valid_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "_select_provider", lambda _provider, **_kwargs: "codex")
    monkeypatch.setattr(
        agent,
        "_run_codex",
        lambda _prompt, _timeout, **_kwargs: {
            "markets": [
                {
                    "country": "us",
                    "language": "English",
                    "keywords": [
                        {"keyword": "  scan   food ", "intent": "scan", "rationale": "direct"},
                        {"keyword": "scan food", "intent": "duplicate", "rationale": "duplicate"},
                    ],
                },
                {
                    "country": "xx",
                    "language": "Other",
                    "keywords": [
                        {"keyword": "ignored", "intent": "ignored", "rationale": "ignored"}
                    ],
                },
            ]
        },
    )

    provider, markets = agent.generate_audit_keywords(
        app_context={"name": "Keto tracker"},
        markets=[{"country": "us", "name": "United States", "language": "English"}],
        provider="auto",
    )

    assert provider == "codex"
    assert list(markets) == ["us"]
    assert [item.keyword for item in markets["us"].keywords] == ["scan food"]


def test_audit_agent_rejects_a_market_in_the_wrong_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "_select_provider", lambda _provider, **_kwargs: "codex")
    monkeypatch.setattr(
        agent,
        "_run_codex",
        lambda _prompt, _timeout, **_kwargs: {
            "markets": [
                {
                    "country": "us",
                    "language": "Spanish",
                    "keywords": [
                        {
                            "keyword": "significado del ascendente",
                            "intent": "ascendant",
                            "rationale": "wrong language",
                        }
                    ],
                }
            ]
        },
    )

    with pytest.raises(agent.AgentError, match="no usable audit keywords"):
        agent.generate_audit_keywords(
            app_context={"name": "Learn astrology"},
            markets=[{"country": "us", "name": "United States", "language": "English"}],
            provider="auto",
        )


def test_localization_specialist_keeps_only_grounded_findings_and_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "_select_provider", lambda _provider, **_kwargs: "codex")
    monkeypatch.setattr(
        agent,
        "_run_codex",
        lambda _prompt, _timeout, **_kwargs: {
            "summary": "Metadata can be tightened.",
            "findings": [
                {
                    "category": "metadata",
                    "tone": "warning",
                    "title": "Repeated metadata",
                    "detail": "Astrology appears twice.",
                    "terms": ["astrology", "invented phrase"],
                    "evidenceIds": ["listing.saved_metadata"],
                },
                {
                    "category": "localization",
                    "tone": "danger",
                    "title": "Unsupported claim",
                    "detail": "This must be discarded.",
                    "terms": ["astrology"],
                    "evidenceIds": ["missing.fact"],
                },
            ],
            "candidatePhrases": [
                {
                    "keyword": "  birth   chart  ",
                    "intent": " chart ",
                    "rationale": " natural wording ",
                }
            ],
        },
    )

    provider, result = agent.generate_audit_localization_review(
        audit_context={"name": "AstroLingo"},
        country="us",
        language="English",
        facts=[
            {
                "id": "listing.saved_metadata",
                "category": "listing",
                "title": "Saved metadata",
                "detail": "Name: Learn Astrology",
                "data": {},
                "terms": ["astrology"],
            }
        ],
        allowed_terms=["astrology", "birth chart"],
        provider="auto",
    )

    assert provider == "codex"
    assert [finding.title for finding in result.findings] == ["Repeated metadata"]
    assert result.findings[0].terms == ["astrology"]
    assert result.findings[0].evidence_ids == ["listing.saved_metadata"]
    assert result.candidate_phrases[0].keyword == "birth chart"


def test_agent_subprocess_closes_stdin_and_reports_timeouts_without_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from local_aso_tracker.services import agent as agent_module

    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, 120)

    monkeypatch.setattr(agent_module.subprocess, "run", fake_run)
    secret_prompt = "PROMPT WITH APP CONTEXT"
    with pytest.raises(agent_module.AgentError) as caught:
        agent_module._run(["/usr/local/bin/claude", "-p", secret_prompt], 120)

    # An inherited, never-closing stdin pipe makes `claude -p` wait until the timeout.
    assert seen["stdin"] is subprocess.DEVNULL
    message = str(caught.value)
    assert "did not answer within 120 seconds" in message
    assert "claude" in message
    assert secret_prompt not in message


def test_claude_timeout_reports_an_expired_login(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from local_aso_tracker.services import agent as agent_module

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--json-schema" in command:
            raise subprocess.TimeoutExpired(command, 120)
        # The quick probe without a schema returns the CLI's auth failure immediately.
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"is_error":true,"result":"Failed to authenticate. '
                'OAuth access token has expired."}'
            ),
            stderr="",
        )

    monkeypatch.setattr(agent_module.subprocess, "run", fake_run)
    with pytest.raises(agent_module.AgentError, match="signed out"):
        agent_module._run_claude("prompt", 120, executable="/usr/local/bin/claude")


def test_claude_timeout_stays_a_timeout_when_signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from local_aso_tracker.services import agent as agent_module

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--json-schema" in command:
            raise subprocess.TimeoutExpired(command, 120)
        return subprocess.CompletedProcess(command, 0, stdout='{"result":"ok"}', stderr="")

    monkeypatch.setattr(agent_module.subprocess, "run", fake_run)
    with pytest.raises(agent_module.AgentError, match="did not answer within 120 seconds"):
        agent_module._run_claude("prompt", 120, executable="/usr/local/bin/claude")
