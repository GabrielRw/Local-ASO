"""Persistence and read models for the competitor rank matrix."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.models import (
    App,
    AppArtwork,
    CompetitorApp,
    CompetitorRank,
    RankCheck,
    Storefront,
)
from local_aso_tracker.repositories.data import latest_pairs, list_targets


def add_competitor_app(
    session: Session,
    *,
    apple_app_id: int,
    name: str,
    artwork_url: str | None,
) -> CompetitorApp:
    item = session.scalar(select(CompetitorApp).where(CompetitorApp.apple_app_id == apple_app_id))
    if item is None:
        item = CompetitorApp(
            apple_app_id=apple_app_id,
            name=" ".join(name.split())[:255],
            artwork_url=artwork_url,
        )
        session.add(item)
    else:
        item.name = " ".join(name.split())[:255]
        item.artwork_url = artwork_url or item.artwork_url
        item.active = True
    session.flush()
    return item


def deactivate_competitor_app(session: Session, apple_app_id: int) -> bool:
    item = session.scalar(select(CompetitorApp).where(CompetitorApp.apple_app_id == apple_app_id))
    if item is None or not item.active:
        return False
    item.active = False
    return True


def active_competitor_apps(session: Session) -> list[CompetitorApp]:
    return list(
        session.scalars(
            select(CompetitorApp)
            .where(CompetitorApp.active.is_(True))
            .order_by(CompetitorApp.created_at, CompetitorApp.id)
        )
    )


def upsert_competitor_rank(
    session: Session,
    *,
    competitor_app_id: int,
    keyword_id: int,
    storefront_id: int,
    device: str,
    checked_at: datetime,
    rank: int | None,
    found: bool,
    result_limit: int,
    status: str,
    error_message: str | None,
) -> CompetitorRank:
    item = session.scalar(
        select(CompetitorRank).where(
            CompetitorRank.competitor_app_id == competitor_app_id,
            CompetitorRank.keyword_id == keyword_id,
            CompetitorRank.storefront_id == storefront_id,
            CompetitorRank.device == device,
        )
    )
    if item is None:
        item = CompetitorRank(
            competitor_app_id=competitor_app_id,
            keyword_id=keyword_id,
            storefront_id=storefront_id,
            device=device,
            checked_at=checked_at,
            rank=rank,
            found=found,
            result_limit=result_limit,
            status=status,
            error_message=error_message,
        )
        session.add(item)
    else:
        item.checked_at = checked_at
        item.rank = rank
        item.found = found
        item.result_limit = result_limit
        item.status = status
        item.error_message = error_message
    return item


def competitor_matrix_payload(
    session: Session,
    *,
    apple_app_id: int,
    country: str,
    device: str,
) -> dict[str, object]:
    app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
    if app is None:
        raise ValueError(f"unknown app ID: {apple_app_id}")
    storefront = session.scalar(select(Storefront).where(Storefront.country_code == country))
    if storefront is None:
        raise ValueError(f"unknown country: {country}")
    primary_artwork = session.get(AppArtwork, app.id)
    competitors = active_competitor_apps(session)
    targets = list_targets(
        session,
        apple_id=apple_app_id,
        country=country,
        device=device,
        active_only=True,
    )
    pairs = latest_pairs(session, targets)
    competitor_ids = [item.id for item in competitors]
    rank_rows = (
        list(
            session.scalars(
                select(CompetitorRank).where(
                    CompetitorRank.competitor_app_id.in_(competitor_ids),
                    CompetitorRank.storefront_id == storefront.id,
                    CompetitorRank.device == device,
                )
            )
        )
        if competitor_ids
        else []
    )
    rank_by_key = {(item.competitor_app_id, item.keyword_id): item for item in rank_rows}
    apps_payload = [
        {
            "appleAppId": app.apple_app_id,
            "name": app.name,
            "artworkUrl": primary_artwork.artwork_url if primary_artwork else None,
            "isPrimary": True,
        },
        *[
            {
                "appleAppId": item.apple_app_id,
                "name": item.name,
                "artworkUrl": item.artwork_url,
                "isPrimary": False,
            }
            for item in competitors
        ],
    ]
    keyword_rows = []
    for target in targets:
        pair = pairs.get(target.id)
        primary_check = pair[0] if pair else None
        cells = [
            _rank_cell(
                app.apple_app_id,
                primary_check,
            ),
            *[
                _rank_cell(
                    competitor.apple_app_id,
                    rank_by_key.get((competitor.id, target.keyword_id)),
                )
                for competitor in competitors
            ],
        ]
        keyword_rows.append(
            {
                "targetId": target.id,
                "keyword": target.keyword.keyword,
                "primaryRank": (
                    primary_check.rank if primary_check and primary_check.found else None
                ),
                "primaryFound": bool(primary_check and primary_check.found),
                "cells": cells,
            }
        )
    keyword_rows.sort(
        key=lambda row: (
            row["primaryRank"] is None,
            row["primaryRank"] if row["primaryRank"] is not None else 10**9,
            str(row["keyword"]).casefold(),
        )
    )
    latest_checked = max(
        (item.checked_at for item in rank_rows),
        default=None,
    )
    return {
        "app": {
            "appleAppId": app.apple_app_id,
            "name": app.name,
        },
        "country": country,
        "device": device,
        "apps": apps_payload,
        "keywords": keyword_rows,
        "competitorCount": len(competitors),
        "lastCheckedAt": _iso(latest_checked),
    }


def _rank_cell(
    app_id: int,
    check: RankCheck | CompetitorRank | None,
) -> dict[str, object]:
    if check is None:
        return {
            "appleAppId": app_id,
            "rank": None,
            "found": False,
            "resultLimit": None,
            "status": "pending",
            "checkedAt": None,
            "error": None,
        }
    return {
        "appleAppId": app_id,
        "rank": check.rank,
        "found": check.found,
        "resultLimit": check.result_limit,
        "status": check.status,
        "checkedAt": _iso(check.checked_at),
        "error": check.error_message,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
