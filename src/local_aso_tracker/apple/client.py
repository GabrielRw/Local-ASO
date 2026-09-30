"""Rate-limited, retrying client for Apple's public iTunes Search API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from local_aso_tracker.apple.schemas import AppleSearchResponse, AppleSoftwareResult
from local_aso_tracker.config import SUPPORTED_DEVICES, validate_device

APPLE_SEARCH_URL = "https://itunes.apple.com/search"
USER_AGENT = "Local-ASO-Tracker/0.5 (+local-only public Apple Search API client)"
logger = logging.getLogger(__name__)


class AppleClientError(RuntimeError):
    """A clear operational error returned by the Apple client."""


class MalformedAppleResponse(AppleClientError):
    """Apple returned JSON that does not match the public response shape."""


@dataclass(frozen=True)
class SearchOutcome:
    response: AppleSearchResponse
    response_time_ms: int
    raw_response_hash: str


@dataclass(frozen=True)
class RankResult:
    rank: int | None
    found: bool
    app: AppleSoftwareResult | None


def extract_rank(response: AppleSearchResponse, apple_app_id: int) -> RankResult:
    """Locate an app by numerical trackId and return its one-based position."""

    for position, result in enumerate(response.results, start=1):
        if result.track_id == apple_app_id:
            return RankResult(rank=position, found=True, app=result)
    return RankResult(rank=None, found=False, app=None)


class AppleSearchClient:
    """Async Apple client with per-run caching, spacing, and safe retries."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        retry_count: int = 3,
        request_delay: float = 1.0,
        result_limit: int = 200,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout = timeout
        self.retry_count = retry_count
        self.request_delay = request_delay
        self.result_limit = result_limit
        self._external_client = client
        self._client: httpx.AsyncClient | None = client
        self._cache: dict[tuple[str, str, str], SearchOutcome] = {}
        self._inflight: dict[tuple[str, str, str], asyncio.Task[SearchOutcome]] = {}
        self._cache_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def __aenter__(self) -> AppleSearchClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._external_client is None and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(self, keyword: str, country: str, device: str = "iphone") -> SearchOutcome:
        """Search the public software entity for one keyword/storefront/device tuple."""

        normalized_device = validate_device(device)
        key = (" ".join(keyword.split()).casefold(), country.lower(), normalized_device)
        async with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._request(keyword=keyword, country=country, device=normalized_device)
                )
                self._inflight[key] = task
        try:
            outcome = await task
        except Exception:
            async with self._cache_lock:
                self._inflight.pop(key, None)
            raise
        async with self._cache_lock:
            self._cache[key] = outcome
            self._inflight.pop(key, None)
        return outcome

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            if self._next_request_at > now:
                await asyncio.sleep(self._next_request_at - now)
            self._next_request_at = time.monotonic() + self.request_delay

    async def _request(self, *, keyword: str, country: str, device: str) -> SearchOutcome:
        if self._client is None:
            raise RuntimeError("AppleSearchClient must be used as an async context manager")
        params: dict[str, str | int] = {
            "term": keyword,
            "country": country,
            "entity": SUPPORTED_DEVICES[device],
            "limit": self.result_limit,
        }
        for attempt in range(self.retry_count + 1):
            await self._wait_for_rate_limit()
            started = time.perf_counter()
            try:
                response = await self._client.get(APPLE_SEARCH_URL, params=params)
                elapsed = round((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                raw: Any = response.json()
                parsed = AppleSearchResponse.model_validate(raw)
                canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
                return SearchOutcome(parsed, elapsed, hashlib.sha256(canonical).hexdigest())
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                raise MalformedAppleResponse(f"malformed Apple response: {exc}") from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                retryable = True
                error: Exception = exc
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                error = exc
            if not retryable or attempt >= self.retry_count:
                message = _friendly_http_error(error)
                logger.debug(
                    "Apple request failed for country=%s device=%s: %s",
                    country,
                    device,
                    message,
                    exc_info=True,
                )
                raise AppleClientError(message) from error
            backoff = (2**attempt) + random.uniform(0, 0.5)
            logger.warning(
                "Retrying Apple request for country=%s device=%s in %.2fs",
                country,
                device,
                backoff,
            )
            await asyncio.sleep(backoff)
        raise AssertionError("retry loop exhausted unexpectedly")


def _friendly_http_error(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "Apple search request timed out"
    if isinstance(error, httpx.HTTPStatusError):
        return f"Apple search returned HTTP {error.response.status_code}"
    if isinstance(error, httpx.NetworkError):
        return "Apple search endpoint is unavailable"
    return "Apple search request failed"
