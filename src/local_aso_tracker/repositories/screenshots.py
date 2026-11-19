"""Persistence for the screenshot studio: sources, captions, renders, and push log."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.models import (
    ScreenshotCaption,
    ScreenshotPushEvent,
    ScreenshotRender,
    ScreenshotSettings,
    ScreenshotSource,
)

DEFAULT_STYLE: dict[str, str] = {
    "background": "#0f172a",
    "backgroundTo": "#1e293b",
    "text": "#ffffff",
    "accent": "#a5b4fc",
}


def get_settings(session: Session, app_id: int) -> ScreenshotSettings:
    settings = session.get(ScreenshotSettings, app_id)
    if settings is None:
        settings = ScreenshotSettings(
            app_id=app_id, main_locale="en-US", style=json.dumps(DEFAULT_STYLE)
        )
        session.add(settings)
        session.flush()
    return settings


def style_of(settings: ScreenshotSettings) -> dict[str, str]:
    try:
        stored = json.loads(settings.style or "{}")
    except json.JSONDecodeError:
        stored = {}
    return {
        **DEFAULT_STYLE,
        **{key: str(value) for key, value in stored.items() if key in DEFAULT_STYLE},
    }


def list_sources(session: Session, app_id: int) -> list[ScreenshotSource]:
    return list(
        session.scalars(
            select(ScreenshotSource)
            .where(ScreenshotSource.app_id == app_id)
            .options(selectinload(ScreenshotSource.captions))
            .order_by(ScreenshotSource.position, ScreenshotSource.id)
        )
    )


def renumber(session: Session, app_id: int, order: list[int] | None = None) -> None:
    sources = list_sources(session, app_id)
    if order:
        rank = {source_id: index for index, source_id in enumerate(order)}
        sources.sort(key=lambda item: (rank.get(item.id, len(rank)), item.position))
    for index, source in enumerate(sources, start=1):
        source.position = index


def upsert_caption(
    session: Session,
    source: ScreenshotSource,
    *,
    locale: str,
    headline: str,
    subline: str,
    origin: str,
) -> ScreenshotCaption:
    caption = next((item for item in source.captions if item.locale == locale), None)
    if caption is None:
        caption = ScreenshotCaption(source_id=source.id, locale=locale)
        session.add(caption)
        source.captions.append(caption)
    caption.headline = headline
    caption.subline = subline
    caption.origin = origin
    caption.updated_at = datetime.now(UTC)
    return caption


def upsert_render(
    session: Session,
    *,
    app_id: int,
    locale: str,
    device: str,
    position: int,
    file_name: str,
    width: int,
    height: int,
    checksum: str,
) -> ScreenshotRender:
    render = session.scalar(
        select(ScreenshotRender).where(
            ScreenshotRender.app_id == app_id,
            ScreenshotRender.locale == locale,
            ScreenshotRender.device == device,
            ScreenshotRender.position == position,
        )
    )
    if render is None:
        render = ScreenshotRender(app_id=app_id, locale=locale, device=device, position=position)
        session.add(render)
    render.file_name = file_name
    render.width = width
    render.height = height
    render.checksum = checksum
    render.rendered_at = datetime.now(UTC)
    session.flush()
    return render


def list_renders(session: Session, app_id: int) -> list[ScreenshotRender]:
    return list(
        session.scalars(
            select(ScreenshotRender)
            .where(ScreenshotRender.app_id == app_id)
            .order_by(ScreenshotRender.locale, ScreenshotRender.device, ScreenshotRender.position)
        )
    )


def delete_renders_beyond(session: Session, app_id: int, count: int) -> None:
    """Drop renders for positions that no longer have a source screenshot."""

    session.execute(
        delete(ScreenshotRender).where(
            ScreenshotRender.app_id == app_id, ScreenshotRender.position > count
        )
    )


def record_push(
    session: Session,
    *,
    app_id: int,
    locale: str,
    device: str,
    status: str,
    before_ids: list[str],
    after_ids: list[str],
    error: str | None = None,
) -> None:
    session.add(
        ScreenshotPushEvent(
            app_id=app_id,
            locale=locale,
            device=device,
            status=status,
            before_ids=json.dumps(before_ids),
            after_ids=json.dumps(after_ids),
            error_message=error,
        )
    )


def recent_pushes(session: Session, app_id: int, limit: int = 30) -> list[ScreenshotPushEvent]:
    return list(
        session.scalars(
            select(ScreenshotPushEvent)
            .where(ScreenshotPushEvent.app_id == app_id)
            .order_by(ScreenshotPushEvent.created_at.desc(), ScreenshotPushEvent.id.desc())
            .limit(limit)
        )
    )
