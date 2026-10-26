"""App-independent niche research board tests."""

import httpx
import pytest
from sqlalchemy.orm import Session

from local_aso_tracker.apple.client import AppleSearchClient
from local_aso_tracker.config import Settings
from local_aso_tracker.repositories.niches import (
    add_niche_country,
    create_niche_board,
    niche_board_payload,
    remove_niche_country,
)
from local_aso_tracker.services.niche_research import refresh_niche_metrics_async


def test_niche_board_persists_countries_keywords_and_pending_metrics(session: Session) -> None:
    board = create_niche_board(
        session,
        name="Keto tracker",
        brief="A calorie tracker for people on keto",
        provider="codex",
        keywords=["keto tracker", "keto app"],
        countries=["us", "gb"],
    )

    assert add_niche_country(session, board, "ca") is True
    assert add_niche_country(session, board, "ca") is False
    payload = niche_board_payload(session, board.id)
    selected = payload["board"]
    assert selected["countries"] == [  # type: ignore[index]
        {"code": "us", "name": "US"},
        {"code": "gb", "name": "GB"},
        {"code": "ca", "name": "CA"},
    ]
    assert selected["keywords"][0]["metrics"][0]["status"] == "pending"  # type: ignore[index]

    assert remove_niche_country(session, board, "gb") is True
    assert remove_niche_country(session, board, "gb") is False
    payload = niche_board_payload(session, board.id)
    assert [item["code"] for item in payload["board"]["countries"]] == ["us", "ca"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_niche_metrics_use_public_apple_ratings(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_aso_tracker.database import run_migrations, session_scope

    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        board = create_niche_board(
            session,
            name="Keto tracker",
            brief="keto",
            provider="codex",
            keywords=["keto tracker"],
            countries=["us", "gb"],
        )
        board_id = board.id

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "resultCount": 3,
                "results": [
                    {"trackId": 1, "userRatingCount": 20_000, "averageUserRating": 4.8},
                    {"trackId": 2, "userRatingCount": 15_000, "averageUserRating": 4.6},
                    {"trackId": 3, "userRatingCount": 10_000, "averageUserRating": 4.5},
                ],
            },
            request=request,
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AppleSearchClient(client=http, request_delay=0)
    result = await refresh_niche_metrics_async(
        board_id,
        Settings(request_delay=0),
        client=client,
    )
    await http.aclose()

    assert calls == 2
    assert result == type(result)(searches=2, failures=0)
    with session_scope() as session:
        payload = niche_board_payload(session, board_id)
    metrics = payload["board"]["keywords"][0]["metrics"]  # type: ignore[index]
    assert [metric["status"] for metric in metrics] == ["success", "success"]
    assert all(metric["volume"] is not None for metric in metrics)


@pytest.mark.asyncio
async def test_niche_metrics_distinguish_no_rating_data_from_check_failure(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_aso_tracker.database import run_migrations, session_scope

    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        board = create_niche_board(
            session,
            name="Keto tracker",
            brief="keto",
            provider="codex",
            keywords=["keto tracker"],
            countries=["fr", "gb"],
        )
        board_id = board.id

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["country"] == "gb":
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "resultCount": 1,
                "results": [{"trackId": 1}],
            },
            request=request,
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AppleSearchClient(client=http, request_delay=0, retry_count=0)
    result = await refresh_niche_metrics_async(
        board_id,
        Settings(request_delay=0),
        client=client,
    )
    await http.aclose()

    assert result == type(result)(searches=2, failures=1)
    with session_scope() as session:
        payload = niche_board_payload(session, board_id)
    metrics = payload["board"]["keywords"][0]["metrics"]  # type: ignore[index]
    assert metrics[0]["status"] == "success"
    assert metrics[0]["volume"] is None
    assert metrics[0]["difficulty"] is None
    assert metrics[1]["status"] == "error"
    assert metrics[1]["error"] == "Apple search returned HTTP 503"
