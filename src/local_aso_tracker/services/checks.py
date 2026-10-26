"""Orchestrate cached Apple searches and persist rank checks."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from local_aso_tracker.apple.client import (
    AppleClientError,
    AppleSearchClient,
    SearchOutcome,
    extract_rank,
)
from local_aso_tracker.config import Settings
from local_aso_tracker.models import RankCheck, RankEstimate, RankTopApp, TrackingTarget
from local_aso_tracker.services.estimates import ESTIMATE_VERSION, estimate_keyword


@dataclass(frozen=True)
class CheckRunResult:
    checks: list[RankCheck]
    searches: int
    failures: int


async def run_checks_async(
    session: Session,
    targets: list[TrackingTarget],
    settings: Settings,
    *,
    concurrency: int | None = None,
    progress: Callable[[int], None] | None = None,
    client: AppleSearchClient | None = None,
) -> CheckRunResult:
    """Query each unique keyword/country/device once and store results for all apps."""

    grouped: dict[tuple[str, str, str], list[TrackingTarget]] = defaultdict(list)
    for target in targets:
        grouped[(target.keyword.keyword, target.storefront.country_code, target.device)].append(
            target
        )
    semaphore = asyncio.Semaphore(concurrency or settings.concurrency)
    owned_client = client or AppleSearchClient(
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
        request_delay=settings.request_delay,
        result_limit=settings.result_limit,
    )

    async def search(
        pair: tuple[str, str, str],
    ) -> tuple[tuple[str, str, str], SearchOutcome | Exception]:
        async with semaphore:
            try:
                return pair, await owned_client.search(*pair)
            except AppleClientError as exc:
                return pair, exc

    async with owned_client:
        results = await asyncio.gather(*(search(pair) for pair in grouped))

    checks: list[RankCheck] = []
    failures = 0
    for pair, outcome in results:
        checked_at = datetime.now(UTC)
        pair_targets = grouped[pair]
        if isinstance(outcome, Exception):
            failures += 1
            for target in pair_targets:
                check = RankCheck(
                    tracking_target_id=target.id,
                    checked_at=checked_at,
                    rank=None,
                    found=False,
                    result_limit=settings.result_limit,
                    total_results_reported=None,
                    response_time_ms=0,
                    status="error",
                    error_message=str(outcome),
                )
                session.add(check)
                checks.append(check)
                if progress:
                    progress(1)
            continue
        for target in pair_targets:
            extracted = extract_rank(outcome.response, target.app.apple_app_id)
            estimates = estimate_keyword(outcome.response.results)
            returned = extracted.app
            check = RankCheck(
                tracking_target_id=target.id,
                checked_at=checked_at,
                rank=extracted.rank,
                found=extracted.found,
                result_limit=settings.result_limit,
                total_results_reported=outcome.response.result_count,
                app_name_returned=returned.track_name if returned else None,
                app_version_returned=returned.version if returned else None,
                app_store_url=returned.track_view_url if returned else None,
                raw_response_hash=outcome.raw_response_hash,
                response_time_ms=outcome.response_time_ms,
                status="success",
                error_message=None,
            )
            check.estimate = RankEstimate(
                volume=estimates.volume,
                difficulty=estimates.difficulty,
                sample_size=estimates.sample_size,
                model_version=ESTIMATE_VERSION,
            )
            check.top_apps = [
                RankTopApp(
                    position=position,
                    track_id=result.track_id,
                    name=result.track_name or f"App {result.track_id}",
                    artwork_url=result.artwork_url_100,
                )
                for position, result in enumerate(
                    outcome.response.results[:5],
                    start=1,
                )
            ]
            session.add(check)
            checks.append(check)
            if progress:
                progress(1)
    session.flush()
    return CheckRunResult(checks=checks, searches=len(grouped), failures=failures)


def run_checks(
    session: Session,
    targets: list[TrackingTarget],
    settings: Settings,
    *,
    concurrency: int | None = None,
    progress: Callable[[int], None] | None = None,
    client: AppleSearchClient | None = None,
) -> CheckRunResult:
    """Synchronous CLI entry point for the async check runner."""

    return asyncio.run(
        run_checks_async(
            session,
            targets,
            settings,
            concurrency=concurrency,
            progress=progress,
            client=client,
        )
    )
