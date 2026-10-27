"""Competitor app management and keyword ranking matrix refresh."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from local_aso_tracker.apple.client import (
    AppleClientError,
    AppleSearchClient,
    SearchOutcome,
    extract_rank,
)
from local_aso_tracker.config import Settings, load_settings, validate_country_code, validate_device
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import (
    App,
    RankCheck,
    RankEstimate,
    RankTopApp,
    TrackingTarget,
)
from local_aso_tracker.repositories.competitors import (
    active_competitor_apps,
    add_competitor_app,
    competitor_matrix_payload,
    deactivate_competitor_app,
    upsert_competitor_rank,
)
from local_aso_tracker.repositories.data import list_targets
from local_aso_tracker.services.estimates import ESTIMATE_VERSION, estimate_keyword

MAX_COMPETITOR_KEYWORDS = 50
_COMPETITOR_REFRESH_LOCK = threading.Lock()


def add_competitor(
    *,
    primary_app_id: int,
    apple_app_id: int,
    name: str,
    artwork_url: str | None,
) -> dict[str, object]:
    """Add or reactivate one competitor app."""

    if apple_app_id <= 0:
        raise ValueError("competitor app ID must be positive")
    if apple_app_id == primary_app_id:
        raise ValueError("the primary app cannot also be a competitor")
    cleaned_name = " ".join(name.split())
    if not cleaned_name or len(cleaned_name) > 255:
        raise ValueError("competitor name is required and must be 255 characters or fewer")
    with session_scope() as session:
        if session.scalar(select(App).where(App.apple_app_id == primary_app_id)) is None:
            raise ValueError(f"unknown primary app ID: {primary_app_id}")
        item = add_competitor_app(
            session,
            apple_app_id=apple_app_id,
            name=cleaned_name,
            artwork_url=artwork_url,
        )
        return {
            "appleAppId": item.apple_app_id,
            "name": item.name,
            "artworkUrl": item.artwork_url,
            "active": item.active,
        }


def remove_competitor(apple_app_id: int) -> dict[str, object]:
    """Remove a competitor from the matrix while retaining local rank data."""

    with session_scope() as session:
        removed = deactivate_competitor_app(session, apple_app_id)
    return {"appleAppId": apple_app_id, "removed": removed}


def competitor_matrix(
    apple_app_id: int,
    country: str,
    device: str,
) -> dict[str, object]:
    """Return the current keyword-by-app ranking matrix."""

    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    with session_scope() as session:
        return competitor_matrix_payload(
            session,
            apple_app_id=apple_app_id,
            country=storefront,
            device=normalized_device,
        )


def refresh_competitor_ranks(
    apple_app_id: int,
    country: str,
    device: str,
) -> dict[str, object]:
    """Refresh primary and competitor ranks from one search per keyword."""

    if not _COMPETITOR_REFRESH_LOCK.acquire(blocking=False):
        raise ValueError("a competitor ranking refresh is already running")
    try:
        return asyncio.run(
            refresh_competitor_ranks_async(
                apple_app_id,
                validate_country_code(country),
                validate_device(device),
                load_settings(),
            )
        )
    finally:
        _COMPETITOR_REFRESH_LOCK.release()


async def refresh_competitor_ranks_async(
    apple_app_id: int,
    country: str,
    device: str,
    settings: Settings,
    *,
    client: AppleSearchClient | None = None,
) -> dict[str, object]:
    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {apple_app_id}")
        competitors = active_competitor_apps(session)
        if not competitors:
            raise ValueError("add at least one competitor before refreshing ranks")
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            country=country,
            device=device,
            active_only=True,
        )
        if not targets:
            raise ValueError("no active keywords are tracked for this market")
        if len(targets) > MAX_COMPETITOR_KEYWORDS:
            raise ValueError(
                f"competitor refresh is limited to {MAX_COMPETITOR_KEYWORDS} keywords per run"
            )
        target_snapshot = [
            {
                "target": target,
                "keyword": target.keyword.keyword,
            }
            for target in targets
        ]

    owned_client = client or AppleSearchClient(
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
        request_delay=settings.request_delay,
        result_limit=settings.result_limit,
    )
    semaphore = asyncio.Semaphore(settings.concurrency)

    async def search(
        entry: dict[str, object],
    ) -> tuple[dict[str, object], SearchOutcome | Exception]:
        target = entry["target"]
        assert isinstance(target, TrackingTarget)
        async with semaphore:
            try:
                return entry, await owned_client.search(
                    str(entry["keyword"]),
                    country,
                    device,
                )
            except AppleClientError as exc:
                return entry, exc

    async with owned_client:
        results = await asyncio.gather(*(search(entry) for entry in target_snapshot))

    checked_at = datetime.now(UTC)
    failures = 0
    competitor_updates = 0
    with session_scope() as session:
        competitors = active_competitor_apps(session)
        for entry, outcome in results:
            target = entry["target"]
            assert isinstance(target, TrackingTarget)
            if isinstance(outcome, Exception):
                failures += 1
                session.add(
                    RankCheck(
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
                )
                for competitor in competitors:
                    upsert_competitor_rank(
                        session,
                        competitor_app_id=competitor.id,
                        keyword_id=target.keyword_id,
                        storefront_id=target.storefront_id,
                        device=device,
                        checked_at=checked_at,
                        rank=None,
                        found=False,
                        result_limit=settings.result_limit,
                        status="error",
                        error_message=str(outcome),
                    )
                    competitor_updates += 1
                continue

            primary = extract_rank(outcome.response, apple_app_id)
            estimates = estimate_keyword(outcome.response.results)
            returned = primary.app
            check = RankCheck(
                tracking_target_id=target.id,
                checked_at=checked_at,
                rank=primary.rank,
                found=primary.found,
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
            for competitor in competitors:
                result = extract_rank(outcome.response, competitor.apple_app_id)
                upsert_competitor_rank(
                    session,
                    competitor_app_id=competitor.id,
                    keyword_id=target.keyword_id,
                    storefront_id=target.storefront_id,
                    device=device,
                    checked_at=checked_at,
                    rank=result.rank,
                    found=result.found,
                    result_limit=settings.result_limit,
                    status="success",
                    error_message=None,
                )
                competitor_updates += 1

    payload = competitor_matrix(apple_app_id, country, device)
    payload["refresh"] = {
        "searches": len(results),
        "failures": failures,
        "competitorRanks": competitor_updates,
        "checkedAt": checked_at.isoformat(),
    }
    return payload
