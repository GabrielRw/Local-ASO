"""Read-only local database queries exposed by the optional MCP server."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.config import validate_country_code, validate_device
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App, AppArtwork, Storefront
from local_aso_tracker.repositories.data import (
    get_listing_metadata,
    latest_pairs,
    list_targets,
    successful_checks,
)
from local_aso_tracker.services.analytics import (
    MetricTrend,
    RankingRow,
    calculate_metric_trends,
    calculate_summary,
)
from local_aso_tracker.services.coverage import TrackedKeyword, analyze_listing_coverage


def list_apps(include_inactive: bool = False) -> dict[str, object]:
    """List locally configured apps and their numerical App Store IDs."""

    with session_scope() as session:
        app_rows = list(session.scalars(select(App).order_by(App.name)).all())
        artwork = {
            item.app_id: item.artwork_url for item in session.scalars(select(AppArtwork)).all()
        }
        apps = [
            {
                "name": app.name,
                "appleAppId": app.apple_app_id,
                "bundleId": app.bundle_id,
                "active": app.active,
                "artworkUrl": artwork.get(app.id),
            }
            for app in app_rows
            if include_inactive or app.active
        ]
    return {"apps": apps, "count": len(apps)}


def list_storefronts(include_inactive: bool = False) -> dict[str, object]:
    """List configured App Store storefronts accepted by the tracker."""

    with session_scope() as session:
        rows = list(session.scalars(select(Storefront).order_by(Storefront.country_code)).all())
        storefronts = [
            {
                "country": item.country_code,
                "name": item.display_name,
                "active": item.active,
            }
            for item in rows
            if include_inactive or item.active
        ]
    return {"storefronts": storefronts, "count": len(storefronts)}


def get_keyword_rankings(
    apple_app_id: int,
    country: str,
    device: str = "iphone",
    keyword: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Return latest stored keyword rankings for one app, storefront, and device."""

    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    with session_scope() as session:
        app = _app(session, apple_app_id)
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            country=storefront,
            device=normalized_device,
            keyword=keyword,
            active_only=True,
        )
        pairs = latest_pairs(session, targets)
        rows = [
            RankingRow(target, pair[0], pair[1])
            for target in targets
            if (pair := pairs.get(target.id))
        ]
        rows.sort(key=lambda row: (row.latest.rank is None, row.latest.rank or 10**9))
        selected = rows[:limit]
        rankings = [
            {
                "keyword": row.target.keyword.keyword,
                "rank": row.latest.rank,
                "found": row.latest.found,
                "resultLimit": row.latest.result_limit,
                "volumeEstimate": (row.latest.estimate.volume if row.latest.estimate else None),
                "difficultyEstimate": (
                    row.latest.estimate.difficulty if row.latest.estimate else None
                ),
                "topApps": [
                    {
                        "position": item.position,
                        "appId": item.track_id,
                        "name": item.name,
                    }
                    for item in row.latest.top_apps
                ],
                "checkedAt": _iso(row.latest.checked_at),
            }
            for row in selected
        ]
    return {
        "app": {"name": app.name, "appleAppId": app.apple_app_id},
        "country": storefront,
        "device": normalized_device,
        "count": len(rankings),
        "rankings": rankings,
    }


def get_app_summary(
    apple_app_id: int,
    country: str,
    device: str = "iphone",
) -> dict[str, object]:
    """Return visibility metrics and 7/30-day changes for one app and storefront."""

    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    with session_scope() as session:
        app = _app(session, apple_app_id)
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            country=storefront,
            device=normalized_device,
            active_only=True,
        )
        pairs = latest_pairs(session, targets)
        rows = [
            RankingRow(target, pair[0], pair[1])
            for target in targets
            if (pair := pairs.get(target.id))
        ]
        history = successful_checks(session, targets)
        now = datetime.now(UTC)
        return {
            "app": {"name": app.name, "appleAppId": app.apple_app_id},
            "country": storefront,
            "device": normalized_device,
            "summary": asdict(calculate_summary(rows)),
            "changes7d": _trend_dicts(
                calculate_metric_trends(
                    targets,
                    pairs,
                    history,
                    cutoff=now - timedelta(days=7),
                )
            ),
            "changes30d": _trend_dicts(
                calculate_metric_trends(
                    targets,
                    pairs,
                    history,
                    cutoff=now - timedelta(days=30),
                )
            ),
        }


def get_listing_coverage(
    apple_app_id: int,
    country: str,
    device: str = "iphone",
) -> dict[str, object]:
    """Analyse saved listing metadata against current tracked rankings."""

    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    with session_scope() as session:
        app = _app(session, apple_app_id)
        metadata = get_listing_metadata(session, apple_app_id, storefront)
        if metadata is None:
            return {
                "app": {"name": app.name, "appleAppId": app.apple_app_id},
                "country": storefront,
                "device": normalized_device,
                "hasMetadata": False,
                "message": (
                    "No subtitle or keyword-field metadata has been saved for this "
                    "app/storefront. Add it in the Listing health tab."
                ),
            }
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            country=storefront,
            device=normalized_device,
            active_only=True,
        )
        pairs = latest_pairs(session, targets)
        tracked = [
            TrackedKeyword(
                keyword=target.keyword.keyword,
                rank=pair[0].rank,
                found=pair[0].found,
                result_limit=pair[0].result_limit,
            )
            for target in targets
            if (pair := pairs.get(target.id))
        ]
        analysis = analyze_listing_coverage(
            metadata.name,
            metadata.subtitle,
            metadata.keyword_field,
            tracked,
        )
        return {
            "app": {"name": app.name, "appleAppId": app.apple_app_id},
            "country": storefront,
            "device": normalized_device,
            "hasMetadata": True,
            "metadata": {
                "name": metadata.name,
                "subtitle": metadata.subtitle,
                "keywords": metadata.keyword_field,
                "updatedAt": _iso(metadata.updated_at),
            },
            "analysis": asdict(analysis),
        }


def _app(session: Session, apple_app_id: int) -> App:
    app = session.scalar(select(App).where(App.apple_app_id == apple_app_id, App.active.is_(True)))
    if app is None:
        raise ValueError(f"unknown active app ID: {apple_app_id}")
    return app


def _trend_dicts(
    trends: dict[str, dict[str, MetricTrend]],
) -> dict[str, dict[str, object]]:
    return {
        key: {name: asdict(value) for name, value in values.items()}
        for key, values in trends.items()
    }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
