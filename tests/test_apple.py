"""Apple response validation and rank extraction tests."""

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from local_aso_tracker.apple.client import AppleSearchClient, extract_rank
from local_aso_tracker.apple.schemas import AppleSearchResponse


def response_payload() -> dict[str, object]:
    return {
        "resultCount": 2,
        "results": [
            {"trackId": 111, "trackName": "Other"},
            {
                "trackId": 6771773264,
                "trackName": "Learn Astrology: AstroLingo",
                "version": "1.2.3",
                "trackViewUrl": "https://apps.apple.com/app/id6771773264",
            },
        ],
    }


def test_rank_extraction_is_one_based() -> None:
    result = extract_rank(AppleSearchResponse.model_validate(response_payload()), 6771773264)
    assert result.found is True
    assert result.rank == 2
    assert result.app is not None and result.app.version == "1.2.3"


def test_app_not_found_is_null_rank() -> None:
    result = extract_rank(AppleSearchResponse.model_validate(response_payload()), 999)
    assert result.found is False
    assert result.rank is None
    assert result.app is None


@pytest.mark.parametrize(
    "payload",
    [{}, {"resultCount": "oops", "results": []}, {"resultCount": 1, "results": [{}]}],
)
def test_malformed_apple_responses_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AppleSearchResponse.model_validate(payload)


@pytest.mark.asyncio
async def test_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json=response_payload(), request=request)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = AppleSearchClient(client=async_client, retry_count=3, request_delay=0)
    async with tracker:
        outcome = await tracker.search("learn astrology", "us")
    await async_client.aclose()
    assert outcome.response.result_count == 2
    assert calls == 3


@pytest.mark.asyncio
async def test_identical_searches_are_cached_within_run() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_payload(), request=request)

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = AppleSearchClient(client=async_client, request_delay=0)
    async with tracker:
        first = await tracker.search(" Learn  Astrology ", "US")
        second = await tracker.search("learn astrology", "us")
    await async_client.aclose()
    assert first is second
    assert calls == 1


@pytest.mark.asyncio
async def test_device_entities_are_separate_cached_searches() -> None:
    entities: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        entities.append(request.url.params["entity"])
        return httpx.Response(200, json=response_payload(), request=request)

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = AppleSearchClient(client=async_client, request_delay=0)
    async with tracker:
        await tracker.search("learn astrology", "us", "iphone")
        await tracker.search("learn astrology", "us", "ipad")
        await tracker.search("learn astrology", "us", "iPad")
    await async_client.aclose()

    assert entities == ["software", "iPadSoftware"]


@pytest.mark.asyncio
async def test_concurrent_identical_searches_share_inflight_request() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return httpx.Response(200, json=response_payload(), request=request)

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = AppleSearchClient(client=async_client, request_delay=0)
    async with tracker:
        outcomes = await asyncio.gather(
            tracker.search("learn astrology", "us"),
            tracker.search("LEARN  ASTROLOGY", "US"),
        )
    await async_client.aclose()
    assert outcomes[0] is outcomes[1]
    assert calls == 1
