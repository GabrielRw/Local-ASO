"""Shared isolated database fixtures."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from local_aso_tracker.models import Base


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as value:
        yield value


@pytest.fixture(autouse=True)
def no_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never probe a real Ollama server; provider tests opt in by patching."""

    from local_aso_tracker.services import agent

    monkeypatch.setattr(agent, "_OLLAMA_CACHE", {})
    monkeypatch.setattr(
        agent,
        "_ollama_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(agent.AgentError("ollama not running")),
    )
