"""Check orchestration and shared-search tests."""

import httpx
import pytest
from sqlalchemy.orm import Session

from local_aso_tracker.apple.client import AppleSearchClient
from local_aso_tracker.config import Settings
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    list_targets,
)
from local_aso_tracker.services.checks import run_checks_async


@pytest.mark.asyncio
async def test_two_apps_share_one_keyword_country_request(session: Session) -> None:
    add_app(session, "One", 1)
    add_app(session, "Two", 2)
    add_keyword(session, "stars")
    add_storefront(session, "us", "United States")
    add_target(session, 1, "stars", "us")
    add_target(session, 2, "stars", "us")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "resultCount": 2,
                "results": [
                    {
                        "trackId": 2,
                        "trackName": "Two",
                        "artworkUrl100": "https://is1-ssl.mzstatic.com/two.png",
                        "userRatingCount": 20_000,
                        "averageUserRating": 4.7,
                    },
                    {
                        "trackId": 1,
                        "trackName": "One",
                        "artworkUrl100": "https://is1-ssl.mzstatic.com/one.png",
                        "userRatingCount": 15_000,
                        "averageUserRating": 4.5,
                    },
                ],
            },
            request=request,
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AppleSearchClient(client=http, request_delay=0)
    result = await run_checks_async(
        session, list_targets(session), Settings(request_delay=0), client=client
    )
    await http.aclose()
    assert calls == 1
    assert result.searches == 1
    assert [item.rank for item in result.checks] == [2, 1]
    assert all(item.estimate is not None for item in result.checks)
    assert all(item.estimate.sample_size == 2 for item in result.checks if item.estimate)
    assert [(item.position, item.name) for item in result.checks[0].top_apps] == [
        (1, "Two"),
        (2, "One"),
    ]
    assert [(item.average_rating, item.rating_count) for item in result.checks[0].top_apps] == [
        (4.7, 20_000),
        (4.5, 15_000),
    ]


@pytest.mark.asyncio
async def test_iphone_and_ipad_use_separate_requests(session: Session) -> None:
    add_app(session, "One", 1)
    add_keyword(session, "stars")
    add_storefront(session, "us", "United States")
    add_target(session, 1, "stars", "us", "iphone")
    add_target(session, 1, "stars", "us", "ipad")
    entities: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        entities.append(request.url.params["entity"])
        return httpx.Response(
            200,
            json={"resultCount": 1, "results": [{"trackId": 1}]},
            request=request,
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AppleSearchClient(client=http, request_delay=0)
    result = await run_checks_async(
        session, list_targets(session), Settings(request_delay=0), client=client
    )
    await http.aclose()

    assert result.searches == 2
    assert entities == ["software", "iPadSoftware"]
