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
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from local_aso_tracker.apple.client import AppleClientError
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
from local_aso_tracker.config import load_settings, validate_country_code, validate_device
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import (
    App,
    Storefront,
    TrackingTarget,
)
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_target,
    latest_pairs,
    list_targets,
    normalize_keyword,
    successful_checks,
)
from local_aso_tracker.repositories.onboarding import complete_onboarding, onboarding_completed
from local_aso_tracker.services.analytics import (
    RankingRow,
    calculate_summary,
    movement,
    opportunity_group,
)
from local_aso_tracker.services.checks import run_checks
from local_aso_tracker.services.health import assess_listing

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
        with session_scope() as session:
            apps = list(session.scalars(select(App).order_by(App.created_at, App.id)).all())
            countries = list(
                session.scalars(select(Storefront).order_by(Storefront.country_code)).all()
            )
            selected = next((item for item in apps if item.apple_app_id == app_id), None)
            if selected is None:
                selected = next((item for item in apps if item.active), apps[0] if apps else None)
            selected_id = selected.apple_app_id if selected else None
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
                "selectedAppId": selected_id,
                "selectedCountry": storefront,
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
                "methodology": (
                    "iPhone ranks use Apple's public software entity and iPad ranks use its "
                    "iPadSoftware entity. Absence means only that the app was not present in "
                    "the retrieved result window."
                ),
            }
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
        keywords = self._parse_keywords(body.get("keywords", body.get("keyword")))
        countries = body.get("countries") or [body.get("country", "us")]
        if not isinstance(countries, list):
            raise ValueError("countries must be a list")
        country_codes = list(dict.fromkeys(validate_country_code(str(item)) for item in countries))
        devices = body.get("devices") or [body.get("device", "iphone")]
        if not isinstance(devices, list):
            raise ValueError("devices must be a list")
        device_codes = list(dict.fromkeys(validate_device(str(item)) for item in devices))
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == app_id))
            if app is None:
                raise ValueError(f"unknown app ID: {app_id}")
            created = 0
            reactivated = 0
            targets_to_check: list[TrackingTarget] = []
            keyword_items = []
            keywords_created = 0
            for keyword in keywords:
                item, keyword_created = add_keyword(session, keyword)
                keyword_items.append(item)
                keywords_created += int(keyword_created)
                for code in country_codes:
                    store = session.scalar(
                        select(Storefront).where(Storefront.country_code == code)
                    )
                    if store is None:
                        raise ValueError(f"unknown country: {code}")
                    for device in device_codes:
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
                        targets_to_check.append(target)
                        created += int(target_created)
                        reactivated += int(was_inactive)
            check_result = run_checks(session, targets_to_check, load_settings())
        return {
            "keywords": [item.keyword for item in keyword_items],
            "keywordsRequested": len(keyword_items),
            "keywordsCreated": keywords_created,
            "targetsCreated": created,
            "targetsReactivated": reactivated,
            "targetsUnchanged": (
                len(keyword_items) * len(country_codes) * len(device_codes) - created - reactivated
            ),
            "automaticCheck": {
                "checks": len(check_result.checks),
                "searches": check_result.searches,
                "failures": check_result.failures,
            },
        }

    def add_app_from_apple(self, body: dict[str, Any]) -> dict[str, object]:
        apple_id = int(body["appleId"])
        country = validate_country_code(str(body.get("country", "us")))
        listing = self.listing(apple_id, country)
        with session_scope() as session:
            item, created = add_app(
                session, listing.track_name, listing.track_id, listing.bundle_id
            )
        return {"created": created, "app": {"name": item.name, "appleAppId": item.apple_app_id}}

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


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve packaged assets and a narrow same-origin JSON API."""

    service = DashboardService()
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
            self._static(parsed.path)
        except (ValueError, KeyError, AppleClientError) as exc:
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
                "/api/apps": self.service.add_app_from_apple,
                "/api/check": self.service.check,
                "/api/targets/deactivate": self.service.deactivate_target,
                "/api/onboarding/complete": self.service.finish_onboarding,
            }
            action = actions.get(parsed.path)
            if action is None:
                self._error(HTTPStatus.NOT_FOUND, "unknown local action")
                return
            self._json(action(body))
        except (ValueError, KeyError, AppleClientError) as exc:
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
    *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True
) -> None:
    """Serve the dashboard until interrupted; bind to loopback by default."""

    server = LocalDashboardServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}"
    print(f"Local ASO dashboard: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
