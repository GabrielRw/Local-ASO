"""Local-only HTTP server and JSON actions for the ASO dashboard."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from local_aso_tracker.apple.client import AppleClientError
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
from local_aso_tracker.config import (
    load_settings,
    update_settings,
    validate_country_code,
    validate_device,
)
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import (
    App,
    AppArtwork,
    Keyword,
    Storefront,
    TrackingTarget,
)
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_target,
    get_listing_metadata,
    latest_pairs,
    list_targets,
    normalize_keyword,
    save_listing_metadata,
    successful_checks,
)
from local_aso_tracker.repositories.niches import (
    add_niche_country,
    add_niche_keywords,
    create_niche_board,
    get_niche_board,
    niche_board_payload,
    remove_niche_country,
)
from local_aso_tracker.repositories.onboarding import complete_onboarding, onboarding_completed
from local_aso_tracker.services.agent import AgentError, generate_keywords, provider_status
from local_aso_tracker.services.analytics import (
    RankingRow,
    calculate_metric_trends,
    calculate_summary,
    movement,
    opportunity_group,
)
from local_aso_tracker.services.automatic_sync import AutomaticSyncWorker
from local_aso_tracker.services.checks import run_checks
from local_aso_tracker.services.coverage import TrackedKeyword, analyze_listing_coverage
from local_aso_tracker.services.estimates import ESTIMATE_VERSION
from local_aso_tracker.services.health import assess_listing
from local_aso_tracker.services.localization import localization_payload
from local_aso_tracker.services.niche_research import refresh_niche_metrics

logger = logging.getLogger(__name__)
STATIC_ROOT = files("local_aso_tracker.web").joinpath("static")


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class DashboardService:
    """Compose dashboard data and execute explicit local mutations."""

    def __init__(self) -> None:
        self._listing_cache: dict[tuple[int, str], tuple[float, AppleListing]] = {}
        self._cache_lock = threading.Lock()

    def listing(self, apple_app_id: int, country: str) -> AppleListing:
        key = (apple_app_id, validate_country_code(country))
        with self._cache_lock:
            cached = self._listing_cache.get(key)
            if cached and time.monotonic() - cached[0] < 3_600:
                return cached[1]
        settings = load_settings()
        value = lookup_listing(
            apple_app_id,
            key[1],
            timeout=settings.request_timeout,
            retry_count=settings.retry_count,
        )
        with self._cache_lock:
            self._listing_cache[key] = (time.monotonic(), value)
        return value

    def bootstrap(self, app_id: int | None, country: str | None) -> dict[str, object]:
        storefront = validate_country_code(country or "us")
        settings = load_settings()
        missing_artwork: list[tuple[int, str]] = []
        with session_scope() as session:
            apps = list(session.scalars(select(App).order_by(App.created_at, App.id)).all())
            active_apps = [item for item in apps if item.active]
            artwork_by_app_id = {
                item.app_id: item.artwork_url for item in session.scalars(select(AppArtwork)).all()
            }
            missing_artwork = [
                (item.apple_app_id, item.name)
                for item in active_apps
                if item.id not in artwork_by_app_id
            ]
            countries = list(
                session.scalars(select(Storefront).order_by(Storefront.country_code)).all()
            )
            selected = next((item for item in active_apps if item.apple_app_id == app_id), None)
            if selected is None:
                selected = active_apps[0] if active_apps else None
            selected_id = selected.apple_app_id if selected else None
            metadata = (
                get_listing_metadata(session, selected_id, storefront)
                if selected_id is not None
                else None
            )
            targets = (
                list_targets(session, apple_id=selected_id, active_only=True) if selected_id else []
            )
            pairs = latest_pairs(session, targets)
            rows = [
                RankingRow(target, pair[0], pair[1])
                for target in targets
                if (pair := pairs.get(target.id)) is not None
            ]
            history = successful_checks(session, targets)
            summary = calculate_summary(rows)
            now = datetime.now(UTC)
            metric_trends = calculate_metric_trends(
                targets,
                pairs,
                history,
                cutoff=now - timedelta(days=7),
            )
            metric_trends_30d = calculate_metric_trends(
                targets,
                pairs,
                history,
                cutoff=now - timedelta(days=30),
            )
            setup_completed = onboarding_completed(session)
            payload: dict[str, object] = {
                "onboarding": {
                    "completed": setup_completed,
                    "shouldOpen": not setup_completed and not apps,
                },
                "apps": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "appleAppId": item.apple_app_id,
                        "bundleId": item.bundle_id,
                        "artworkUrl": artwork_by_app_id.get(item.id),
                        "active": item.active,
                    }
                    for item in apps
                ],
                "countries": [
                    {
                        "code": item.country_code,
                        "name": item.display_name,
                        "active": item.active,
                    }
                    for item in countries
                ],
                "devices": [
                    {"code": "iphone", "name": "iPhone"},
                    {"code": "ipad", "name": "iPad"},
                ],
                "agentProviders": [asdict(item) for item in provider_status()],
                "defaultAgentProvider": settings.agent_provider,
                "selectedAppId": selected_id,
                "selectedCountry": storefront,
                "listingMetadata": (
                    {
                        "name": metadata.name,
                        "subtitle": metadata.subtitle,
                        "keywords": metadata.keyword_field,
                        "updatedAt": _iso_utc(metadata.updated_at),
                    }
                    if metadata
                    else None
                ),
                "rankings": [self._ranking(row) for row in rows],
                "targetCounts": {
                    f"{item.country_code}:{device}": sum(
                        target.storefront.country_code == item.country_code
                        and target.device == device
                        for target in targets
                    )
                    for item in countries
                    for device in ("iphone", "ipad")
                },
                "history": [
                    {
                        "targetId": check.tracking_target_id,
                        "keyword": check.tracking_target.keyword.keyword
                        if check.tracking_target
                        else "",
                        "country": check.tracking_target.storefront.country_code
                        if check.tracking_target
                        else "",
                        "device": check.tracking_target.device
                        if check.tracking_target
                        else "iphone",
                        "rank": check.rank,
                        "found": check.found,
                        "resultLimit": check.result_limit,
                        "checkedAt": _iso_utc(check.checked_at),
                    }
                    for check in history
                ],
                "summary": asdict(summary),
                "metricTrends": {
                    key: {name: asdict(trend) for name, trend in values.items()}
                    for key, values in metric_trends.items()
                },
                "metricTrends30d": {
                    key: {name: asdict(trend) for name, trend in values.items()}
                    for key, values in metric_trends_30d.items()
                },
                "methodology": (
                    "iPhone ranks use Apple's public software entity and iPad ranks use its "
                    "iPadSoftware entity. Absence means only that the app was not present in "
                    "the retrieved result window."
                ),
                "estimateMethodology": {
                    "version": ESTIMATE_VERSION,
                    "window": "Up to the first 10 returned app results",
                    "volume": (
                        "Position-weighted audience score from app rating counts. This is not "
                        "Apple search volume or a download estimate."
                    ),
                    "difficulty": (
                        "Competition score from top-result rating strength, rating quality, and "
                        "how many of the first five results expose ratings."
                    ),
                },
            }
        discovered_artwork: dict[int, str] = {}
        for missing_app_id, missing_name in missing_artwork:
            try:
                artwork_url = self.listing(missing_app_id, storefront).artwork_url
            except AppleClientError:
                logger.debug(
                    "Could not retrieve artwork for app %s (%s)",
                    missing_app_id,
                    missing_name,
                )
                continue
            if artwork_url:
                discovered_artwork[missing_app_id] = artwork_url
        if discovered_artwork:
            with session_scope() as session:
                for discovered_app_id, artwork_url in discovered_artwork.items():
                    app = session.scalar(select(App).where(App.apple_app_id == discovered_app_id))
                    if app is not None:
                        artwork = session.get(AppArtwork, app.id)
                        if artwork is None:
                            session.add(AppArtwork(app_id=app.id, artwork_url=artwork_url))
                        else:
                            artwork.artwork_url = artwork_url
            payload_apps = payload.get("apps")
            if isinstance(payload_apps, list):
                for app_payload in payload_apps:
                    if isinstance(app_payload, dict):
                        payload_app_id = app_payload.get("appleAppId")
                        if isinstance(payload_app_id, int):
                            discovered = discovered_artwork.get(payload_app_id)
                            if discovered:
                                app_payload["artworkUrl"] = discovered
        if selected:
            try:
                listing = self.listing(selected.apple_app_id, storefront)
                payload["listing"] = self._listing_dict(listing)
                payload["health"] = assess_listing(listing).as_dict()
            except AppleClientError as exc:
                payload["listingError"] = str(exc)
                payload["listing"] = self._fallback_listing(selected)
        return payload

    def finish_onboarding(self, _body: dict[str, Any]) -> dict[str, object]:
        with session_scope() as session:
            complete_onboarding(session)
        return {"completed": True, "shouldOpen": False}

    def save_agent_provider(self, body: dict[str, Any]) -> dict[str, object]:
        provider = str(body.get("provider", "auto")).strip().lower()
        if provider not in {"auto", "codex", "claude"}:
            raise ValueError("agent provider must be auto, codex, or claude")
        if provider != "auto":
            available = {item.id: item.available for item in provider_status()}
            if not available.get(provider, False):
                raise ValueError(f"{provider} CLI is not installed or not available on PATH")
        settings = update_settings(agent_provider=provider)
        return {"provider": settings.agent_provider}

    def compare(self, app_id: int, competitor_id: int, country: str) -> dict[str, object]:
        primary = self.listing(app_id, country)
        competitor = self.listing(competitor_id, country)
        return {
            "primary": self._listing_dict(primary),
            "competitor": self._listing_dict(competitor),
            "primaryHealth": assess_listing(primary).as_dict(),
            "competitorHealth": assess_listing(competitor).as_dict(),
        }

    def add_keyword_targets(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        raw_groups = body.get("groups")
        if raw_groups is None:
            target_groups = [
                (
                    self._parse_keywords(body.get("keywords", body.get("keyword"))),
                    self._parse_countries(body.get("countries") or [body.get("country", "us")]),
                    self._parse_devices(body.get("devices") or [body.get("device", "iphone")]),
                )
            ]
        else:
            if not isinstance(raw_groups, list) or not raw_groups:
                raise ValueError("groups must be a non-empty list")
            target_groups = []
            for group in raw_groups:
                if not isinstance(group, dict):
                    raise ValueError("each group must be an object")
                target_groups.append(
                    (
                        self._parse_keywords(group.get("keywords")),
                        self._parse_countries(group.get("countries")),
                        self._parse_devices(
                            group.get("devices")
                            or body.get("devices")
                            or [body.get("device", "iphone")]
                        ),
                    )
                )
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == app_id))
            if app is None:
                raise ValueError(f"unknown app ID: {app_id}")
            created = 0
            reactivated = 0
            requested_slots = 0
            targets_to_check: dict[int, TrackingTarget] = {}
            keyword_items: dict[str, Keyword] = {}
            keywords_created = 0
            for keywords, country_codes, device_codes in target_groups:
                for keyword in keywords:
                    item, keyword_created = add_keyword(session, keyword)
                    keyword_items.setdefault(item.normalized_keyword, item)
                    keywords_created += int(keyword_created)
                    for code in country_codes:
                        store = session.scalar(
                            select(Storefront).where(Storefront.country_code == code)
                        )
                        if store is None:
                            raise ValueError(f"unknown country: {code}")
                        for device in device_codes:
                            requested_slots += 1
                            existing = session.scalar(
                                select(TrackingTarget).where(
                                    TrackingTarget.app_id == app.id,
                                    TrackingTarget.keyword_id == item.id,
                                    TrackingTarget.storefront_id == store.id,
                                    TrackingTarget.device == device,
                                )
                            )
                            was_inactive = existing is not None and not existing.active
                            target, target_created = add_target(
                                session, app_id, item.keyword, code, device
                            )
                            targets_to_check[target.id] = target
                            created += int(target_created)
                            reactivated += int(was_inactive)
            check_result = run_checks(session, list(targets_to_check.values()), load_settings())
        return {
            "keywords": [item.keyword for item in keyword_items.values()],
            "keywordsRequested": len(keyword_items),
            "keywordsCreated": keywords_created,
            "targetsCreated": created,
            "targetsReactivated": reactivated,
            "targetsUnchanged": requested_slots - created - reactivated,
            "automaticCheck": {
                "checks": len(check_result.checks),
                "searches": check_result.searches,
                "failures": check_result.failures,
            },
        }

    def localize_keywords(self, body: dict[str, Any]) -> dict[str, object]:
        keywords = self._parse_keywords(body.get("keywords", body.get("keyword")))
        countries = self._parse_countries(body.get("countries") or [body.get("country", "us")])
        with session_scope() as session:
            known = set(session.scalars(select(Storefront.country_code)))
        unknown = sorted(set(countries) - known)
        if unknown:
            raise ValueError(f"unknown country: {unknown[0]}")
        return localization_payload(keywords, countries)

    def niche(self, board_id: int | None = None) -> dict[str, object]:
        settings = load_settings()
        with session_scope() as session:
            payload = niche_board_payload(session, board_id)
        payload["providers"] = [asdict(provider) for provider in provider_status()]
        payload["defaultProvider"] = settings.agent_provider
        return payload

    def generate_niche_board(self, body: dict[str, Any]) -> dict[str, object]:
        brief = " ".join(str(body.get("brief", "")).split())
        if not brief:
            raise ValueError("describe the niche before generating keywords")
        if len(brief) > 1_000:
            raise ValueError("niche description must be 1000 characters or fewer")
        settings = load_settings()
        provider = str(body.get("provider") or settings.agent_provider)
        with session_scope() as session:
            active = list(
                session.scalars(select(Storefront.country_code).where(Storefront.active.is_(True)))
            )
            requested_countries = body.get("countries")
            if isinstance(requested_countries, list) and requested_countries:
                countries = self._parse_countries(requested_countries)
            else:
                countries = [
                    country for country in settings.default_countries if country in active
                ][:5]
                if not countries:
                    countries = active[:5]
            if set(countries) - set(active):
                raise ValueError("all board countries must be active storefronts")
        generated = generate_keywords(
            brief=brief,
            count=10,
            provider=provider,
            timeout=settings.agent_timeout,
        )
        with session_scope() as session:
            board = create_niche_board(
                session,
                name=brief[:80],
                brief=brief,
                provider=generated.provider,
                keywords=generated.keywords,
                countries=countries,
            )
            board_id = board.id
        check = refresh_niche_metrics(board_id, settings)
        payload = self.niche(board_id)
        payload["generation"] = {
            "provider": generated.provider,
            "keywords": generated.keywords,
            "check": asdict(check),
        }
        return payload

    def add_niche_agent_keywords(self, body: dict[str, Any]) -> dict[str, object]:
        board_id = int(body["boardId"])
        instruction = " ".join(str(body.get("instruction", "")).split())
        if not instruction:
            raise ValueError("describe the keywords to add")
        settings = load_settings()
        with session_scope() as session:
            board = get_niche_board(session, board_id)
            if board is None:
                raise ValueError(f"unknown niche board: {board_id}")
            brief = board.brief
            existing = [keyword.keyword for keyword in board.keywords]
        match = re.search(r"\b([1-9]|10)\b", instruction)
        count = int(match.group(1)) if match else 5
        generated = generate_keywords(
            brief=f"{brief}. Additional request: {instruction}",
            existing_keywords=existing,
            count=count,
            provider=str(body.get("provider") or settings.agent_provider),
            timeout=settings.agent_timeout,
        )
        with session_scope() as session:
            board = get_niche_board(session, board_id)
            if board is None:
                raise ValueError(f"unknown niche board: {board_id}")
            added = add_niche_keywords(session, board, generated.keywords)
            added_ids = {item.id for item in added}
        check = (
            refresh_niche_metrics(board_id, settings, keyword_ids=added_ids) if added_ids else None
        )
        payload = self.niche(board_id)
        payload["agent"] = {
            "provider": generated.provider,
            "keywords": generated.keywords,
            "check": asdict(check) if check else None,
        }
        return payload

    def add_niche_market(self, body: dict[str, Any]) -> dict[str, object]:
        board_id = int(body["boardId"])
        country = validate_country_code(str(body["country"]))
        settings = load_settings()
        with session_scope() as session:
            storefront = session.scalar(
                select(Storefront).where(
                    Storefront.country_code == country,
                    Storefront.active.is_(True),
                )
            )
            if storefront is None:
                raise ValueError(f"unknown active country: {country}")
            board = get_niche_board(session, board_id)
            if board is None:
                raise ValueError(f"unknown niche board: {board_id}")
            added = add_niche_country(session, board, country)
        check = refresh_niche_metrics(board_id, settings, countries={country}) if added else None
        payload = self.niche(board_id)
        payload["countryChange"] = {
            "country": country,
            "added": added,
            "check": asdict(check) if check else None,
        }
        return payload

    def remove_niche_market(self, body: dict[str, Any]) -> dict[str, object]:
        board_id = int(body["boardId"])
        country = validate_country_code(str(body["country"]))
        with session_scope() as session:
            board = get_niche_board(session, board_id)
            if board is None:
                raise ValueError(f"unknown niche board: {board_id}")
            removed = remove_niche_country(session, board, country)
        payload = self.niche(board_id)
        payload["countryChange"] = {"country": country, "removed": removed}
        return payload

    def check_niche_board(self, body: dict[str, Any]) -> dict[str, object]:
        board_id = int(body["boardId"])
        settings = load_settings()
        result = refresh_niche_metrics(board_id, settings)
        payload = self.niche(board_id)
        payload["check"] = asdict(result)
        return payload

    def save_listing_coverage(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        country = validate_country_code(str(body["country"]))
        device = validate_device(str(body.get("device", "iphone")))
        name = " ".join(str(body.get("name", "")).split())
        subtitle = " ".join(str(body.get("subtitle", "")).split())
        keywords = " ".join(str(body.get("keywords", "")).split())
        if not name:
            raise ValueError("listing name is required")
        if len(name) > 30:
            raise ValueError("listing name must be 30 characters or fewer")
        if len(subtitle) > 30:
            raise ValueError("subtitle must be 30 characters or fewer")
        if len(keywords) > 100:
            raise ValueError("keyword field must be 100 characters or fewer")
        with session_scope() as session:
            metadata = save_listing_metadata(
                session,
                app_id,
                country,
                name=name,
                subtitle=subtitle,
                keyword_field=keywords,
            )
            targets = list_targets(
                session,
                apple_id=app_id,
                country=country,
                device=device,
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
            analysis = analyze_listing_coverage(name, subtitle, keywords, tracked)
        return {
            "metadata": {
                "name": metadata.name,
                "subtitle": metadata.subtitle,
                "keywords": metadata.keyword_field,
                "updatedAt": _iso_utc(metadata.updated_at),
            },
            "country": country,
            "device": device,
            "analysis": asdict(analysis),
        }

    def add_app_from_apple(self, body: dict[str, Any]) -> dict[str, object]:
        apple_id = int(body["appleId"])
        country = validate_country_code(str(body.get("country", "us")))
        listing = self.listing(apple_id, country)
        with session_scope() as session:
            item, created = add_app(
                session,
                listing.track_name,
                listing.track_id,
                listing.bundle_id,
                listing.artwork_url,
            )
        return {"created": created, "app": {"name": item.name, "appleAppId": item.apple_app_id}}

    def deactivate_app(self, body: dict[str, Any]) -> dict[str, object]:
        apple_id = int(body["appleId"])
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == apple_id))
            if app is None:
                raise ValueError(f"unknown app ID: {apple_id}")
            app.active = False
            return {"removed": apple_id, "name": app.name}

    def deactivate_target(self, body: dict[str, Any]) -> dict[str, object]:
        target_id = int(body["targetId"])
        with session_scope() as session:
            target = session.get(TrackingTarget, target_id)
            if target is None:
                raise ValueError(f"unknown tracking target: {target_id}")
            target.active = False
        return {"deactivated": target_id}

    def check(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        country = str(body["country"]) if body.get("country") else None
        keyword = str(body["keyword"]) if body.get("keyword") else None
        device = str(body["device"]) if body.get("device") else None
        settings = load_settings()
        with session_scope() as session:
            targets = list_targets(
                session,
                apple_id=app_id,
                country=country,
                keyword=keyword,
                device=device,
                active_only=True,
            )
            if not targets:
                raise ValueError("no matching active targets")
            result = run_checks(session, targets, settings)
            return {
                "checks": len(result.checks),
                "searches": result.searches,
                "failures": result.failures,
            }

    @staticmethod
    def _ranking(row: RankingRow) -> dict[str, object]:
        return {
            "targetId": row.target.id,
            "keyword": row.target.keyword.keyword,
            "country": row.target.storefront.country_code,
            "device": row.target.device,
            "rank": row.latest.rank,
            "found": row.latest.found,
            "resultLimit": row.latest.result_limit,
            "volumeEstimate": row.latest.estimate.volume if row.latest.estimate else None,
            "difficultyEstimate": (row.latest.estimate.difficulty if row.latest.estimate else None),
            "estimateSampleSize": (
                row.latest.estimate.sample_size if row.latest.estimate else None
            ),
            "topApps": [
                {
                    "position": item.position,
                    "appId": item.track_id,
                    "name": item.name,
                    "artworkUrl": item.artwork_url,
                }
                for item in row.latest.top_apps
            ],
            "previousRank": row.previous.rank if row.previous else None,
            "previousFound": row.previous.found if row.previous else None,
            "change": movement(row.latest, row.previous),
            "checkedAt": _iso_utc(row.latest.checked_at),
            "opportunity": opportunity_group(row.latest),
        }

    @staticmethod
    def _listing_dict(item: AppleListing) -> dict[str, object]:
        return {
            "appleAppId": item.track_id,
            "name": item.track_name,
            "bundleId": item.bundle_id,
            "seller": item.seller_name,
            "version": item.version,
            "url": item.track_view_url,
            "artworkUrl": item.artwork_url,
            "genre": item.genre,
            "description": item.description,
            "screenshots": item.screenshot_urls + item.ipad_screenshot_urls,
            "screenshotCount": item.screenshot_count,
            "screenshotStatus": "available" if item.screenshot_count else "not_exposed",
            "averageRating": item.average_rating,
            "ratingCount": item.rating_count,
            "updatedAt": _iso_utc(item.current_version_release_date),
            "releasedAt": _iso_utc(item.release_date),
            "languages": item.language_codes,
            "fileSizeBytes": item.file_size_bytes,
            "price": item.formatted_price,
            "minimumOsVersion": item.minimum_os_version,
            "descriptionLength": len(item.description),
        }

    @staticmethod
    def _fallback_listing(item: App) -> dict[str, object]:
        return {
            "appleAppId": item.apple_app_id,
            "name": item.name,
            "bundleId": item.bundle_id,
            "artworkUrl": None,
            "genre": None,
            "version": None,
            "price": None,
            "url": None,
            "screenshots": [],
            "screenshotCount": 0,
            "screenshotStatus": "unavailable",
        }

    @staticmethod
    def _parse_keywords(value: object) -> list[str]:
        raw_values = value if isinstance(value, list) else [value]
        keywords: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            for candidate in re.split(r"[,\n]+", str(raw or "")):
                cleaned = " ".join(candidate.split())
                if not cleaned:
                    continue
                normalized = normalize_keyword(cleaned)
                if normalized not in seen:
                    seen.add(normalized)
                    keywords.append(cleaned)
        if not keywords:
            raise ValueError("enter at least one keyword")
        if len(keywords) > 100:
            raise ValueError("add at most 100 keywords at once")
        return keywords

    @staticmethod
    def _parse_countries(value: object) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("countries must be a non-empty list")
        return list(dict.fromkeys(validate_country_code(str(item)) for item in value))

    @staticmethod
    def _parse_devices(value: object) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("devices must be a non-empty list")
        return list(dict.fromkeys(validate_device(str(item)) for item in value))


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve packaged assets and a narrow same-origin JSON API."""

    service = DashboardService()
    sync_worker: AutomaticSyncWorker | None = None
    server_version = "LocalASODashboard/0.5"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/bootstrap":
                query = parse_qs(parsed.query)
                app_id = int(query["appId"][0]) if query.get("appId") else None
                country = query.get("country", [None])[0]
                self._json(self.service.bootstrap(app_id, country))
                return
            if parsed.path == "/api/compare":
                query = parse_qs(parsed.query)
                self._json(
                    self.service.compare(
                        int(query["appId"][0]),
                        int(query["competitorId"][0]),
                        query.get("country", ["us"])[0],
                    )
                )
                return
            if parsed.path == "/api/niche":
                query = parse_qs(parsed.query)
                board_id = int(query["boardId"][0]) if query.get("boardId") else None
                self._json(self.service.niche(board_id))
                return
            if parsed.path == "/api/sync-status":
                worker = self.sync_worker
                self._json(
                    {
                        "sync": (
                            worker.status_payload() if worker is not None else {"state": "disabled"}
                        )
                    }
                )
                return
            self._static(parsed.path)
        except (ValueError, KeyError, AppleClientError, AgentError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            logger.debug("Dashboard GET failed", exc_info=True)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"local dashboard error: {exc}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            actions = {
                "/api/keywords": self.service.add_keyword_targets,
                "/api/keywords/localize": self.service.localize_keywords,
                "/api/listing-metadata": self.service.save_listing_coverage,
                "/api/apps": self.service.add_app_from_apple,
                "/api/apps/deactivate": self.service.deactivate_app,
                "/api/check": self.service.check,
                "/api/targets/deactivate": self.service.deactivate_target,
                "/api/onboarding/complete": self.service.finish_onboarding,
                "/api/settings/agent": self.service.save_agent_provider,
                "/api/niche/generate": self.service.generate_niche_board,
                "/api/niche/check": self.service.check_niche_board,
                "/api/niche/agent-keywords": self.service.add_niche_agent_keywords,
                "/api/niche/countries/add": self.service.add_niche_market,
                "/api/niche/countries/remove": self.service.remove_niche_market,
            }
            action = actions.get(parsed.path)
            if action is None:
                self._error(HTTPStatus.NOT_FOUND, "unknown local action")
                return
            self._json(action(body))
        except (ValueError, KeyError, AppleClientError, AgentError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            logger.debug("Dashboard POST failed", exc_info=True)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"local dashboard error: {exc}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("request body must be JSON under 1 MB")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _static(self, request_path: str) -> None:
        path = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        pure = PurePosixPath(path)
        if ".." in pure.parts or pure.is_absolute():
            self._error(HTTPStatus.NOT_FOUND, "asset not found")
            return
        resource = STATIC_ROOT.joinpath(*pure.parts)
        if not resource.is_file():
            self._error(HTTPStatus.NOT_FOUND, "asset not found")
            return
        content = resource.read_bytes()
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self._headers(content_type, len(content))
        self.end_headers()
        self.wfile.write(content)

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self._headers("application/json; charset=utf-8", len(content))
        self.end_headers()
        self.wfile.write(content)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https://*.mzstatic.com data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
        )

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("Dashboard HTTP: " + format, *args)


class LocalDashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_dashboard(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    mcp_enabled: bool = True,
    mcp_port: int = 8766,
    open_browser: bool = True,
) -> None:
    """Serve the dashboard until interrupted; bind to loopback by default."""

    from local_aso_tracker.mcp_server import MCPRuntime

    server = LocalDashboardServer((host, port), DashboardHandler)
    sync_worker = AutomaticSyncWorker()
    DashboardHandler.sync_worker = sync_worker
    sync_worker.start()
    mcp_runtime = MCPRuntime(port=mcp_port) if mcp_enabled else None
    if mcp_runtime is not None:
        if mcp_runtime.start():
            print(f"Local ASO MCP: {mcp_runtime.url}", flush=True)
        else:
            print(f"Warning: MCP endpoint unavailable on port {mcp_port}.", flush=True)
            mcp_runtime = None
    url = f"http://{host}:{port}"
    print(f"Local ASO dashboard: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nDashboard stopped.", flush=True)
    finally:
        sync_worker.stop()
        DashboardHandler.sync_worker = None
        server.server_close()
        if mcp_runtime is not None:
            mcp_runtime.stop()
