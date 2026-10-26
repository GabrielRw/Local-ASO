"""Refresh Apple-public-data market estimates for niche research boards."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from local_aso_tracker.apple.client import AppleClientError, AppleSearchClient, SearchOutcome
from local_aso_tracker.config import Settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import NicheBoard
from local_aso_tracker.repositories.niches import get_niche_board, upsert_niche_metric
from local_aso_tracker.services.estimates import estimate_keyword


@dataclass(frozen=True)
class NicheCheckResult:
    searches: int
    failures: int


@dataclass(frozen=True)
class NicheSearchTarget:
    keyword_id: int
    keyword: str
    country: str


async def refresh_niche_metrics_async(
    board_id: int,
    settings: Settings,
    *,
    client: AppleSearchClient | None = None,
    keyword_ids: set[int] | None = None,
    countries: set[str] | None = None,
) -> NicheCheckResult:
    """Refresh all keyword/country pairs in one niche board."""

    with session_scope() as session:
        board = get_niche_board(session, board_id)
        if board is None:
            raise ValueError(f"unknown niche board: {board_id}")
        targets = [
            NicheSearchTarget(
                keyword_id=keyword.id,
                keyword=keyword.keyword,
                country=market.country_code,
            )
            for keyword in sorted(board.keywords, key=lambda item: item.position)
            if keyword_ids is None or keyword.id in keyword_ids
            for market in sorted(board.markets, key=lambda item: item.position)
            if countries is None or market.country_code in countries
        ]
    if not targets:
        return NicheCheckResult(searches=0, failures=0)

    owned_client = client or AppleSearchClient(
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
        request_delay=settings.request_delay,
        result_limit=settings.result_limit,
    )
    semaphore = asyncio.Semaphore(settings.concurrency)

    async def search(
        target: NicheSearchTarget,
    ) -> tuple[NicheSearchTarget, SearchOutcome | Exception]:
        async with semaphore:
            try:
                return target, await owned_client.search(
                    target.keyword,
                    target.country,
                    "iphone",
                )
            except AppleClientError as exc:
                return target, exc

    async with owned_client:
        results = await asyncio.gather(*(search(target) for target in targets))

    failures = 0
    with session_scope() as session:
        for target, outcome in results:
            if isinstance(outcome, Exception):
                failures += 1
                upsert_niche_metric(
                    session,
                    keyword_id=target.keyword_id,
                    country=target.country,
                    device="iphone",
                    volume=None,
                    difficulty=None,
                    sample_size=0,
                    status="error",
                    error=str(outcome),
                )
                continue
            estimates = estimate_keyword(outcome.response.results)
            upsert_niche_metric(
                session,
                keyword_id=target.keyword_id,
                country=target.country,
                device="iphone",
                volume=estimates.volume,
                difficulty=estimates.difficulty,
                sample_size=estimates.sample_size,
                status="success",
            )
        board = session.scalar(select(NicheBoard).where(NicheBoard.id == board_id))
        if board is not None:
            board.updated_at = datetime.now(UTC)
    return NicheCheckResult(searches=len(targets), failures=failures)


def refresh_niche_metrics(
    board_id: int,
    settings: Settings,
    *,
    client: AppleSearchClient | None = None,
    keyword_ids: set[int] | None = None,
    countries: set[str] | None = None,
) -> NicheCheckResult:
    """Synchronous entry point for the dashboard HTTP server."""

    return asyncio.run(
        refresh_niche_metrics_async(
            board_id,
            settings,
            client=client,
            keyword_ids=keyword_ids,
            countries=countries,
        )
    )
