"""Competitor matrix persistence and rank refresh tests."""

from pathlib import Path

import httpx
import pytest

from local_aso_tracker.apple.client import AppleSearchClient
from local_aso_tracker.config import Settings
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import seed_catalog, seed_targets
from local_aso_tracker.services.competitors import (
    add_competitor,
    competitor_matrix,
    refresh_competitor_ranks_async,
    remove_competitor,
)


@pytest.fixture
def competitor_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)


@pytest.mark.asyncio
async def test_competitor_matrix_adds_columns_and_refreshes_ranks(
    competitor_database: None,
) -> None:
    added = add_competitor(
        primary_app_id=6771773264,
        apple_app_id=111,
        name="First app",
        artwork_url="https://is1-ssl.mzstatic.com/first.png",
    )
    assert added["active"] is True

    initial = competitor_matrix(6771773264, "us", "iphone")
    assert [app["name"] for app in initial["apps"]] == [  # type: ignore[index]
        "AstroLingo",
        "First app",
    ]
    assert initial["keywords"][0]["cells"][1]["status"] == "pending"  # type: ignore[index]

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "resultCount": 3,
                "results": [
                    {"trackId": 111, "trackName": "First app"},
                    {"trackId": 222, "trackName": "Second app"},
                    {"trackId": 6771773264, "trackName": "AstroLingo"},
                ],
            },
            request=request,
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AppleSearchClient(client=http, request_delay=0)
    result = await refresh_competitor_ranks_async(
        6771773264,
        "us",
        "iphone",
        Settings(request_delay=0),
        client=client,
    )
    await http.aclose()

    assert calls == 15
    assert result["refresh"]["searches"] == 15  # type: ignore[index]
    assert result["refresh"]["failures"] == 0  # type: ignore[index]
    first = result["keywords"][0]  # type: ignore[index]
    assert first["cells"][0]["rank"] == 3
    assert first["cells"][1]["rank"] == 1


def test_competitor_can_be_removed_without_deleting_history(
    competitor_database: None,
) -> None:
    add_competitor(
        primary_app_id=6771773264,
        apple_app_id=111,
        name="First app",
        artwork_url=None,
    )

    assert remove_competitor(111) == {"appleAppId": 111, "removed": True}
    payload = competitor_matrix(6771773264, "us", "iphone")
    assert payload["competitorCount"] == 0
    assert len(payload["apps"]) == 1  # type: ignore[arg-type]
