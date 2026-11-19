"""Screenshot studio: import raw screenshots, caption them per locale, store renders.

Rendering itself happens in the dashboard (a canvas in the web view), which shapes every
script correctly with the system's fonts; the server stores and validates the results.
Files live under ``<data dir>/screenshots/<app id>/`` and never outside it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.apple.app_store_connect import (
    EDITABLE_VERSION_STATES,
    AppStoreConnectClient,
    AppStoreConnectError,
)
from local_aso_tracker.config import data_dir, load_settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App, ScreenshotSource, Storefront
from local_aso_tracker.repositories.screenshots import (
    DEFAULT_STYLE,
    get_settings,
    list_renders,
    list_sources,
    recent_pushes,
    record_push,
    renumber,
    style_of,
    upsert_caption,
    upsert_render,
)
from local_aso_tracker.services.agent import (
    generate_screenshot_captions,
    translate_screenshot_captions,
)
from local_aso_tracker.services.storefronts import APP_STORE_LOCALE_LANGUAGE, MARKETS
from local_aso_tracker.utils.images import image_info

MAX_SOURCE_BYTES = 15 * 1024 * 1024
MAX_SOURCES = 10
# App Store Connect's required sizes; other sizes are scaled down from these by Apple.
DEVICES: dict[str, dict[str, Any]] = {
    "iphone": {
        "label": 'iPhone 6.9"',
        "displayType": "APP_IPHONE_67",
        "width": 1320,
        "height": 2868,
    },
    "ipad": {
        "label": 'iPad 13"',
        "displayType": "APP_IPAD_PRO_3GEN_129",
        "width": 2064,
        "height": 2752,
    },
}


def screenshots_dir(app_id: int) -> Path:
    return data_dir() / "screenshots" / str(app_id)


def _contained(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("screenshot path is outside the screenshots folder")
    return resolved


def _app(session: Session, apple_app_id: int) -> App:
    app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
    if app is None:
        raise ValueError(f"unknown app ID: {apple_app_id}")
    return app


def studio_locales(session: Session, main_locale: str) -> list[dict[str, object]]:
    """The main locale plus the listing locale of every active storefront."""

    active = list(
        session.scalars(select(Storefront.country_code).where(Storefront.active.is_(True)))
    )
    by_locale: dict[str, list[str]] = {main_locale: []}
    for code in sorted(active):
        found = MARKETS.get(code)
        if found:
            by_locale.setdefault(found.locale, []).append(code)
    return [
        {
            "locale": locale,
            "language": APP_STORE_LOCALE_LANGUAGE.get(locale, locale),
            "countries": countries,
            "isMain": locale == main_locale,
        }
        for locale, countries in by_locale.items()
    ]


def studio_payload(apple_app_id: int) -> dict[str, object]:
    with session_scope() as session:
        app = _app(session, apple_app_id)
        settings = get_settings(session, app.id)
        sources = list_sources(session, app.id)
        renders = list_renders(session, app.id)
        return {
            "appId": apple_app_id,
            "mainLocale": settings.main_locale,
            "style": style_of(settings),
            "devices": DEVICES,
            "locales": studio_locales(session, settings.main_locale),
            "sources": [
                {
                    "id": source.id,
                    "position": source.position,
                    "width": source.width,
                    "height": source.height,
                    "name": source.original_name,
                    "url": f"/api/screenshots/file/source/{source.id}",
                    "captions": {
                        caption.locale: {
                            "headline": caption.headline,
                            "subline": caption.subline,
                            "origin": caption.origin,
                        }
                        for caption in source.captions
                    },
                }
                for source in sources
            ],
            "renders": [
                {
                    "id": render.id,
                    "locale": render.locale,
                    "device": render.device,
                    "position": render.position,
                    "url": f"/api/screenshots/file/render/{render.id}",
                    "renderedAt": render.rendered_at.isoformat(),
                }
                for render in renders
            ],
            "pushEvents": [
                {
                    "locale": event.locale,
                    "device": event.device,
                    "status": event.status,
                    "error": event.error_message,
                    "createdAt": event.created_at.isoformat(),
                    "uploaded": len(json.loads(event.after_ids or "[]")),
                }
                for event in recent_pushes(session, app.id)
            ],
        }


def add_source(apple_app_id: int, data: bytes, *, original_name: str = "") -> dict[str, object]:
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("screenshots must be 15 MB or smaller")
    kind, width, height = image_info(data)
    if width < 320 or height < 320:
        raise ValueError("that image is too small to be an app screenshot")
    with session_scope() as session:
        app = _app(session, apple_app_id)
        if len(list_sources(session, app.id)) >= MAX_SOURCES:
            raise ValueError(f"the App Store shows at most {MAX_SOURCES} screenshots per device")
        folder = screenshots_dir(app.id) / "sources"
        folder.mkdir(parents=True, exist_ok=True)
        file_name = f"{uuid.uuid4().hex}.{'png' if kind == 'png' else 'jpg'}"
        _contained(folder / file_name, screenshots_dir(app.id)).write_bytes(data)
        source = ScreenshotSource(
            app_id=app.id,
            position=10_000,
            file_name=file_name,
            original_name=original_name[:255],
            content_type=f"image/{kind}",
            width=width,
            height=height,
        )
        session.add(source)
        session.flush()
        renumber(session, app.id)
    return studio_payload(apple_app_id)


def delete_source(apple_app_id: int, source_id: int) -> dict[str, object]:
    with session_scope() as session:
        app = _app(session, apple_app_id)
        source = session.get(ScreenshotSource, source_id)
        if source is None or source.app_id != app.id:
            raise ValueError("unknown screenshot")
        path = screenshots_dir(app.id) / "sources" / source.file_name
        session.delete(source)
        session.flush()
        renumber(session, app.id)
        _contained(path, screenshots_dir(app.id)).unlink(missing_ok=True)
    return studio_payload(apple_app_id)


def reorder_sources(apple_app_id: int, order: list[int]) -> dict[str, object]:
    with session_scope() as session:
        app = _app(session, apple_app_id)
        renumber(session, app.id, order)
    return studio_payload(apple_app_id)


def save_caption(
    apple_app_id: int, source_id: int, *, locale: str, headline: str, subline: str
) -> dict[str, object]:
    headline = " ".join(headline.split())[:60]
    subline = " ".join(subline.split())[:120]
    with session_scope() as session:
        app = _app(session, apple_app_id)
        source = session.get(ScreenshotSource, source_id)
        if source is None or source.app_id != app.id:
            raise ValueError("unknown screenshot")
        upsert_caption(
            session, source, locale=locale, headline=headline, subline=subline, origin="user"
        )
    return studio_payload(apple_app_id)


def save_settings(
    apple_app_id: int, *, main_locale: str | None, style: dict[str, str] | None
) -> dict[str, object]:
    with session_scope() as session:
        app = _app(session, apple_app_id)
        settings = get_settings(session, app.id)
        if main_locale is not None:
            if main_locale not in APP_STORE_LOCALE_LANGUAGE:
                raise ValueError("unknown App Store locale")
            settings.main_locale = main_locale
        if style is not None:
            clean = {
                key: str(style[key])[:9]
                for key in DEFAULT_STYLE
                if key in style and str(style[key]).startswith("#")
            }
            settings.style = json.dumps({**style_of(settings), **clean})
    return studio_payload(apple_app_id)


def _agent_settings(provider: object) -> dict[str, Any]:
    settings = load_settings()
    return {
        "provider": str(provider or settings.agent_provider),
        "codex_path": settings.agent_codex_path,
        "claude_path": settings.agent_claude_path,
        "timeout": settings.agent_timeout,
    }


def draft_captions(
    apple_app_id: int, listing: dict[str, str], *, provider: object = None
) -> dict[str, object]:
    """Ask the local AI for main-locale captions; existing user-written captions are kept."""

    with session_scope() as session:
        app = _app(session, apple_app_id)
        main_locale = get_settings(session, app.id).main_locale
        sources = list_sources(session, app.id)
        notes = [source.original_name for source in sources]
        count = len(sources)
    if not count:
        raise ValueError("import screenshots before drafting captions")
    _selected, captions = generate_screenshot_captions(
        listing=listing,
        count=count,
        locale=main_locale,
        language=APP_STORE_LOCALE_LANGUAGE.get(main_locale, "English"),
        notes=notes,
        **_agent_settings(provider),
    )
    with session_scope() as session:
        app = _app(session, apple_app_id)
        for source in list_sources(session, app.id):
            existing = next((item for item in source.captions if item.locale == main_locale), None)
            if existing is not None and existing.origin == "user" and existing.headline:
                continue
            if source.position in captions:
                headline, subline = captions[source.position]
                upsert_caption(
                    session,
                    source,
                    locale=main_locale,
                    headline=headline,
                    subline=subline,
                    origin="ai",
                )
    return studio_payload(apple_app_id)


def translate_captions(
    apple_app_id: int, locales: list[str], *, provider: object = None
) -> dict[str, object]:
    """Translate main-locale captions into the given locales (overwrites AI captions only)."""

    with session_scope() as session:
        app = _app(session, apple_app_id)
        main_locale = get_settings(session, app.id).main_locale
        main: dict[int, tuple[str, str]] = {}
        for source in list_sources(session, app.id):
            caption = next((item for item in source.captions if item.locale == main_locale), None)
            if caption is not None and caption.headline:
                main[source.position] = (caption.headline, caption.subline)
    if not main:
        raise ValueError("write or draft the main captions first")
    targets = {
        locale: APP_STORE_LOCALE_LANGUAGE[locale]
        for locale in locales
        if locale in APP_STORE_LOCALE_LANGUAGE and locale != main_locale
    }
    if not targets:
        raise ValueError("choose at least one other locale to translate into")
    _selected, translated = translate_screenshot_captions(
        captions=main,
        source_language=APP_STORE_LOCALE_LANGUAGE.get(main_locale, "English"),
        targets=targets,
        **_agent_settings(provider),
    )
    with session_scope() as session:
        app = _app(session, apple_app_id)
        for source in list_sources(session, app.id):
            for locale, by_position in translated.items():
                existing = next((item for item in source.captions if item.locale == locale), None)
                if existing is not None and existing.origin == "user" and existing.headline:
                    continue
                if source.position in by_position:
                    headline, subline = by_position[source.position]
                    upsert_caption(
                        session,
                        source,
                        locale=locale,
                        headline=headline,
                        subline=subline,
                        origin="ai",
                    )
    return studio_payload(apple_app_id)


def save_render(
    apple_app_id: int, *, locale: str, device: str, position: int, data: bytes
) -> dict[str, object]:
    """Store one rendered PNG; it must be exactly the App Store size for the device."""

    spec = DEVICES.get(device)
    if spec is None:
        raise ValueError("device must be iphone or ipad")
    if locale not in APP_STORE_LOCALE_LANGUAGE:
        raise ValueError("unknown App Store locale")
    kind, width, height = image_info(data)
    if kind != "png" or (width, height) != (spec["width"], spec["height"]):
        raise ValueError(
            f"{spec['label']} screenshots must be {spec['width']}x{spec['height']} PNG"
        )
    with session_scope() as session:
        app = _app(session, apple_app_id)
        if not 1 <= position <= len(list_sources(session, app.id)):
            raise ValueError("no screenshot at that position")
        folder = screenshots_dir(app.id) / "renders" / locale / device
        folder.mkdir(parents=True, exist_ok=True)
        relative = f"renders/{locale}/{device}/{position:02d}.png"
        _contained(screenshots_dir(app.id) / relative, screenshots_dir(app.id)).write_bytes(data)
        render = upsert_render(
            session,
            app_id=app.id,
            locale=locale,
            device=device,
            position=position,
            file_name=relative,
            width=width,
            height=height,
            checksum=hashlib.md5(data, usedforsecurity=False).hexdigest(),
        )
        return {"id": render.id, "url": f"/api/screenshots/file/render/{render.id}"}


def file_for(kind: str, item_id: int) -> tuple[Path, str]:
    """Path and content type of a stored source or render (for the preview route)."""

    from local_aso_tracker.models import ScreenshotRender

    with session_scope() as session:
        if kind == "source":
            source = session.get(ScreenshotSource, item_id)
            if source is None:
                raise ValueError("unknown screenshot")
            root = screenshots_dir(source.app_id)
            return _contained(root / "sources" / source.file_name, root), source.content_type
        if kind == "render":
            render = session.get(ScreenshotRender, item_id)
            if render is None:
                raise ValueError("unknown screenshot")
            root = screenshots_dir(render.app_id)
            return _contained(root / render.file_name, root), "image/png"
    raise ValueError("unknown screenshot kind")


def push_to_app_store_connect(
    apple_app_id: int,
    *,
    locales: list[str],
    devices: list[str],
    client: AppStoreConnectClient | None = None,
) -> dict[str, object]:
    """Replace each chosen locale's screenshot sets with the stored renders.

    Requires an editable App Store version. Every locale and device pair is attempted and logged;
    one failure doesn't stop the others.
    """

    with session_scope() as session:
        app = _app(session, apple_app_id)
        if not app.bundle_id:
            raise ValueError("this app has no bundle ID; add it again from Apple to fetch it")
        bundle_id = app.bundle_id
        app_db_id = app.id
        renders = list_renders(session, app.id)
        files: dict[tuple[str, str], list[tuple[str, Path]]] = {}
        for render in renders:
            if render.locale in locales and render.device in devices:
                files.setdefault((render.locale, render.device), []).append(
                    (
                        f"{render.position:02d}_{render.device}_{render.locale}.png",
                        screenshots_dir(app.id) / render.file_name,
                    )
                )
    if not files:
        raise ValueError("render the screenshots for these locales and devices first")
    owned = client is None
    asc = client or AppStoreConnectClient(load_settings())
    results: list[dict[str, object]] = []
    try:
        snapshot = asc.snapshot(bundle_id=bundle_id)
        if snapshot.version_state not in EDITABLE_VERSION_STATES:
            raise ValueError(
                f"the App Store version is {snapshot.version_state}; screenshots can only be "
                "changed on a version that is being prepared"
            )
        for (locale, device), items in sorted(files.items()):
            localization = snapshot.localizations.get(locale)
            before: list[str] = []
            after: list[str] = []
            error: str | None = None
            if localization is None or not localization.version_localization_id:
                error = (
                    f"{locale} doesn't exist in App Store Connect yet; push its listing text first"
                )
            else:
                try:
                    before, after = asc.replace_screenshots(
                        version_localization_id=localization.version_localization_id,
                        display_type=str(DEVICES[device]["displayType"]),
                        files=[(name, path.read_bytes()) for name, path in sorted(items)],
                    )
                except AppStoreConnectError as exc:
                    error = str(exc)
            with session_scope() as session:
                record_push(
                    session,
                    app_id=app_db_id,
                    locale=locale,
                    device=device,
                    status="failed" if error else "success",
                    before_ids=before,
                    after_ids=after,
                    error=error,
                )
            results.append(
                {"locale": locale, "device": device, "uploaded": len(after), "error": error}
            )
    finally:
        if owned:
            asc.__exit__(None, None, None)
    return {"results": results, "versionState": snapshot.version_state}
