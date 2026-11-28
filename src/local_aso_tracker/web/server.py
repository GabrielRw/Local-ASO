"""Local-only HTTP server and JSON actions for the ASO dashboard."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker import licensing
from local_aso_tracker.apple.ads import AppleAdsError
from local_aso_tracker.apple.app_store_connect import (
    AppStoreConnectClient,
    AppStoreConnectError,
    connection_status,
)
from local_aso_tracker.apple.client import AppleClientError
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
from local_aso_tracker.config import (
    Settings,
    exports_dir,
    load_settings,
    update_settings,
    validate_country_code,
    validate_device,
)
from local_aso_tracker.database import session_scope
from local_aso_tracker.desktop import load_desktop_settings, save_desktop_settings
from local_aso_tracker.models import (
    App,
    AppArtwork,
    Keyword,
    KeywordPopularity,
    Storefront,
    TrackingTarget,
)
from local_aso_tracker.reports.fastlane import export_fastlane_metadata
from local_aso_tracker.repositories.audits import (
    active_audit_run,
    audit_dashboard_payload,
    create_audit_run,
    get_audit_run,
)
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    competitor_brand_keys,
    filter_targets_due_for_check,
    get_listing_metadata,
    latest_pairs,
    list_targets,
    normalize_keyword,
    save_listing_metadata,
    set_competitor_brand,
    successful_checks,
)
from local_aso_tracker.repositories.keyword_popularity import popularity_lookup
from local_aso_tracker.repositories.niches import (
    add_niche_country,
    add_niche_keywords,
    create_niche_board,
    get_niche_board,
    niche_board_payload,
    remove_niche_country,
)
from local_aso_tracker.repositories.onboarding import complete_onboarding, onboarding_completed
from local_aso_tracker.services import background_sync, pricing
from local_aso_tracker.services.agent import (
    CLI_PROVIDER_IDS,
    AgentError,
    check_provider,
    generate_keyword_translations,
    generate_keywords,
    ollama_models,
    open_sign_in,
    provider_payload,
    provider_status,
    test_provider,
    validate_ollama_url,
    validate_provider_id,
)
from local_aso_tracker.services.analytics import (
    RankingRow,
    calculate_metric_trends,
    calculate_summary,
    movement,
)
from local_aso_tracker.services.apple_ads import (
    apple_ads_status,
    discover_accounts,
    select_account,
    sync_apple_ads,
)
from local_aso_tracker.services.audits import AuditWorker
from local_aso_tracker.services.automatic_sync import AutomaticSyncWorker
from local_aso_tracker.services.checks import run_checks
from local_aso_tracker.services.competitors import (
    add_competitor,
    competitor_matrix,
    refresh_competitor_ranks,
    remove_competitor,
)
from local_aso_tracker.services.coverage import (
    TrackedKeyword,
    analyze_distribution_strategy,
    analyze_listing_coverage,
)
from local_aso_tracker.services.estimates import ESTIMATE_VERSION
from local_aso_tracker.services.health import assess_listing
from local_aso_tracker.services.keyword_popularity import (
    popularity_configured,
    popularity_opportunity,
)
from local_aso_tracker.services.listing_localization import (
    approve_localization,
    generate_localization_drafts,
    listing_localization_studio,
    push_localization,
    save_main_storefront,
    update_localization_fields,
)
from local_aso_tracker.services.localization import Translator, localization_payload
from local_aso_tracker.services.localization_targets import COUNTRY_PRIMARY_LANGUAGE
from local_aso_tracker.services.niche_research import localize_board_terms, refresh_niche_metrics
from local_aso_tracker.services.storefronts import MARKETS, require_market

logger = logging.getLogger(__name__)
STATIC_ROOT = files("local_aso_tracker.web").joinpath("static")


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _agent_paths_payload(settings: Settings) -> dict[str, object]:
    """Saved CLI paths per provider plus the local Ollama connection, for the agent sheet."""

    return {
        **{
            provider_id: str(getattr(settings, f"agent_{provider_id}_path"))
            for provider_id in CLI_PROVIDER_IDS
        },
        "ollama": {
            "url": settings.ollama_url,
            "model": settings.ollama_model,
            "models": ollama_models(),
        },
    }


def _popularity_key(row: RankingRow) -> tuple[str, str]:
    return (row.target.keyword.normalized_keyword, row.target.storefront.country_code.upper())


class DashboardService:
    """Compose dashboard data and execute explicit local mutations."""

    def __init__(self) -> None:
        self._listing_cache: dict[tuple[int, str], tuple[float, AppleListing]] = {}
        self._cache_lock = threading.Lock()
        self.audit_worker = AuditWorker()

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
        if value.bundle_id:
            # Apps added before bundle IDs were stored get theirs from Apple's listing.
            with session_scope() as session:
                stored = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
                if stored is not None and not stored.bundle_id:
                    stored.bundle_id = value.bundle_id
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
            coverage_strategy = (
                analyze_distribution_strategy(
                    metadata.name,
                    metadata.subtitle,
                    metadata.keyword_field,
                    goal=metadata.channel_goal,
                    brand_term=metadata.brand_term,
                )
                if metadata is not None
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
                "markets": [
                    {"code": item.code, "name": item.name, "language": item.language}
                    for item in sorted(MARKETS.values(), key=lambda value: value.name)
                ],
                "agentProviders": [
                    provider_payload(item)
                    for item in provider_status(
                        codex_path=settings.agent_codex_path,
                        claude_path=settings.agent_claude_path,
                    )
                ],
                "defaultAgentProvider": settings.agent_provider,
                "selectedAppId": selected_id,
                "selectedCountry": storefront,
                "listingMetadata": (
                    {
                        "name": metadata.name,
                        "subtitle": metadata.subtitle,
                        "keywords": metadata.keyword_field,
                        "channelGoal": metadata.channel_goal,
                        "brandTerm": metadata.brand_term,
                        "updatedAt": _iso_utc(metadata.updated_at),
                    }
                    if metadata
                    else None
                ),
                "rankings": self._rankings(session, rows),
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
                payload["health"] = assess_listing(listing, strategy=coverage_strategy).as_dict()
            except AppleClientError as exc:
                payload["listingError"] = str(exc)
                payload["listing"] = self._fallback_listing(selected)
        return payload

    def finish_onboarding(self, _body: dict[str, Any]) -> dict[str, object]:
        with session_scope() as session:
            complete_onboarding(session)
        return {"completed": True, "shouldOpen": False}

    def save_agent_provider(self, body: dict[str, Any]) -> dict[str, object]:
        provider = validate_provider_id(str(body.get("provider", "auto")))
        changes: dict[str, object] = {"agent_provider": provider}
        paths = self._agent_paths_from_body(body)
        for provider_id, value in paths.items():
            changes[f"agent_{provider_id}_path"] = value
        if "ollamaUrl" in body:
            changes["ollama_url"] = validate_ollama_url(str(body["ollamaUrl"]))
        if "ollamaModel" in body:
            model = " ".join(str(body["ollamaModel"]).split())
            if len(model) > 200:
                raise ValueError("ollamaModel must be 200 characters or fewer")
            changes["ollama_model"] = model
        if provider != "auto":
            current = load_settings()
            merged = {
                provider_id: str(
                    changes.get(
                        f"agent_{provider_id}_path",
                        getattr(current, f"agent_{provider_id}_path"),
                    )
                )
                for provider_id in CLI_PROVIDER_IDS
            }
            test_provider(
                provider,
                paths=merged,
                ollama_url=str(changes.get("ollama_url", current.ollama_url)),
                ollama_model=str(changes.get("ollama_model", current.ollama_model)),
            )
        settings = update_settings(**changes)
        return {"provider": settings.agent_provider, "agentPaths": _agent_paths_payload(settings)}

    @staticmethod
    def _agent_paths_from_body(body: dict[str, Any]) -> dict[str, str]:
        """Accept `paths: {provider: path}` and the legacy `codexPath`/`claudePath` keys."""

        raw: dict[str, object] = {}
        if isinstance(body.get("paths"), dict):
            raw.update(body["paths"])
        for legacy, provider_id in (("codexPath", "codex"), ("claudePath", "claude")):
            if legacy in body:
                raw[provider_id] = body[legacy]
        paths: dict[str, str] = {}
        for provider_id, value in raw.items():
            if provider_id not in CLI_PROVIDER_IDS:
                raise ValueError(f"unknown CLI provider: {provider_id}")
            text = " ".join(str(value).split())
            if len(text) > 500:
                raise ValueError(f"{provider_id} path must be 500 characters or fewer")
            paths[str(provider_id)] = text
        return paths

    def audit(
        self,
        app_id: int,
        run_id: int | None = None,
        country: str | None = None,
        device: str | None = None,
    ) -> dict[str, object]:
        settings = load_settings()
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == app_id))
            if app is None:
                raise ValueError(f"unknown app ID: {app_id}")
            payload = audit_dashboard_payload(
                session,
                app_id=app.id,
                run_id=run_id,
                country_code=validate_country_code(country) if country else None,
                device=validate_device(device) if device else None,
            )
        payload["appId"] = app_id
        payload["providers"] = [
            provider_payload(item)
            for item in provider_status(
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
            )
        ]
        payload["defaultProvider"] = settings.agent_provider
        selected_run = payload.get("run")
        selected_country = (
            str(selected_run.get("country"))
            if isinstance(selected_run, dict) and selected_run.get("country")
            else country or "us"
        )
        payload["auditLanguage"] = COUNTRY_PRIMARY_LANGUAGE.get(
            selected_country,
            "English",
        )
        payload["agentPaths"] = _agent_paths_payload(settings)
        return payload

    def start_audit(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        scope = str(body.get("scope", "country")).strip().lower()
        if scope != "country":
            raise ValueError("audits are available per country only")
        device = validate_device(str(body.get("device", "iphone")))
        country = validate_country_code(str(body.get("country", "us")))
        settings = load_settings()
        requested_provider = validate_provider_id(
            str(body.get("provider") or settings.agent_provider)
        )
        providers = {
            item.id: item.available
            for item in provider_status(
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
            )
        }
        if requested_provider != "auto" and not providers.get(requested_provider, False):
            raise ValueError(f"{requested_provider} is not installed or not available on this Mac")
        if requested_provider == "auto" and not any(providers.values()):
            raise ValueError(
                "Install the Claude, Codex, Gemini, or OpenCode CLI, or run Ollama, before "
                "running an audit"
            )
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == app_id))
            if app is None:
                raise ValueError(f"unknown app ID: {app_id}")
            if not app.active:
                raise ValueError("choose an active app before running an audit")
            active_countries = list(
                session.scalars(
                    select(Storefront.country_code)
                    .where(Storefront.active.is_(True))
                    .order_by(Storefront.country_code)
                )
            )
            if country not in active_countries:
                raise ValueError(f"unknown active country: {country}")
            existing = active_audit_run(
                session,
                app_id=app.id,
                device=device,
                country_code=country,
            )
            if existing is not None:
                return self.audit(app_id, existing.id, country, device)
            countries = [country]
            run = create_audit_run(
                session,
                app_id=app.id,
                scope=scope,
                country_code=country,
                device=device,
                provider=requested_provider,
                country_codes=countries,
            )
            run_id = run.id
        self.audit_worker.start(run_id)
        return self.audit(app_id, run_id, country, device)

    def cancel_audit(self, body: dict[str, Any]) -> dict[str, object]:
        run_id = int(body["runId"])
        app_id = int(body["appId"])
        self.audit_worker.cancel(run_id)
        return self.audit(app_id, run_id)

    def expand_audit(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        run_id = int(body["runId"])
        country = validate_country_code(str(body["country"]))
        instruction = " ".join(str(body.get("instruction", "")).split())
        if not instruction:
            raise ValueError("describe what kind of keywords to discover")
        if len(instruction) > 1_000:
            raise ValueError("discovery instruction must be 1000 characters or fewer")
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None or run.app is None or run.app.apple_app_id != app_id:
                raise ValueError("audit does not belong to the selected app")
        added = self.audit_worker.runner.expand_country(run_id, country, instruction)
        payload = self.audit(app_id, run_id)
        payload["iteration"] = {
            "country": country,
            "added": added,
            "instruction": instruction,
        }
        return payload

    def test_agent_provider(self, body: dict[str, Any]) -> dict[str, object]:
        settings = load_settings()
        return test_provider(
            str(body.get("provider") or settings.agent_provider),
            paths=self._agent_paths_from_body(body),
            ollama_url=str(body["ollamaUrl"]) if "ollamaUrl" in body else None,
            ollama_model=str(body["ollamaModel"]) if "ollamaModel" in body else None,
            timeout=15.0,
        )

    def check_agent_provider(self, body: dict[str, Any]) -> dict[str, object]:
        """Is this AI tool installed, signed in, and answering? (one tiny request)"""

        return check_provider(str(body.get("provider", "")))

    def sign_in_agent_provider(self, body: dict[str, Any]) -> dict[str, object]:
        """Open Terminal with the tool's sign-in command; the user finishes there."""

        return open_sign_in(str(body.get("provider", "")))

    def localization_studio(self, app_id: int, country: str) -> dict[str, object]:
        settings = load_settings()
        with session_scope() as session:
            payload = listing_localization_studio(
                session,
                app_id=app_id,
                current_country=validate_country_code(country),
                settings=settings,
            )
        payload["providers"] = [
            provider_payload(item)
            for item in provider_status(
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
            )
        ]
        payload["defaultProvider"] = settings.agent_provider
        return payload

    def save_app_store_connect_settings(
        self,
        body: dict[str, Any],
    ) -> dict[str, object]:
        issuer_id = " ".join(str(body.get("issuerId", "")).split())
        key_id = " ".join(str(body.get("keyId", "")).split())
        key_path = str(body.get("keyPath", "")).strip()
        if len(issuer_id) > 200 or len(key_id) > 100 or len(key_path) > 1_000:
            raise ValueError("App Store Connect credentials are too long")
        settings = update_settings(
            app_store_connect_issuer_id=issuer_id,
            app_store_connect_key_id=key_id,
            app_store_connect_key_path=key_path,
        )
        return connection_status(settings)

    def test_app_store_connect(self, _body: dict[str, Any]) -> dict[str, object]:
        settings = load_settings()
        with AppStoreConnectClient(settings) as client:
            result = client.test()
        result["status"] = connection_status(settings)
        return result

    def set_localization_main_storefront(
        self,
        body: dict[str, Any],
    ) -> dict[str, object]:
        app_id = int(body["appId"])
        country = validate_country_code(str(body["country"]))
        save_main_storefront(app_id=app_id, country=country)
        return self.localization_studio(app_id, country)

    def generate_localization(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        main_country = validate_country_code(str(body["mainCountry"]))
        target_countries = body.get("targetCountries")
        if not isinstance(target_countries, list) or not target_countries:
            raise ValueError("select at least one target country")
        targets = [validate_country_code(str(country)) for country in target_countries]
        settings = load_settings()
        result = generate_localization_drafts(
            app_id=app_id,
            main_country=main_country,
            target_countries=targets,
            provider=str(body.get("provider") or settings.agent_provider),
            settings=settings,
        )
        return {
            "drafts": result.drafts,
            "iterations": result.iterations,
        }

    def approve_listing_localization(
        self,
        body: dict[str, Any],
    ) -> dict[str, object]:
        return approve_localization(draft_id=int(body["draftId"]))

    def update_listing_localization(
        self,
        body: dict[str, Any],
    ) -> dict[str, object]:
        fields = body.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("localization fields must be an object")
        return update_localization_fields(
            draft_id=int(body["draftId"]),
            fields={str(key): str(value) for key, value in fields.items()},
        )

    def push_listing_localization(
        self,
        body: dict[str, Any],
    ) -> dict[str, object]:
        licensing.require("listing-push")
        return push_localization(
            draft_id=int(body["draftId"]),
            settings=load_settings(),
        )

    def apple_ads(self, app_id: int | None, country: str, device: str) -> dict[str, object]:
        return apple_ads_status(app_id, country, device)

    def check_paid_keyword_rank(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        keyword = " ".join(str(body["keyword"]).split())
        if not keyword:
            raise ValueError("keyword is required")
        country = validate_country_code(str(body["country"]))
        device = validate_device(str(body.get("device", "iphone")))
        country_name = " ".join(str(body.get("countryName") or country.upper()).split())[:100]
        with session_scope() as session:
            storefront = session.scalar(
                select(Storefront).where(Storefront.country_code == country)
            )
            if storefront is None:
                add_storefront(session, country, country_name or country.upper())
            elif not storefront.active:
                storefront.active = True
        result = self.add_keyword_targets(
            {
                "appId": app_id,
                "keywords": keyword,
                "countries": [country],
                "devices": [device],
            }
        )
        with session_scope() as session:
            target = list_targets(
                session,
                apple_id=app_id,
                keyword=keyword,
                country=country,
                device=device,
                active_only=True,
            )[0]
            pair = latest_pairs(session, [target]).get(target.id)
            check = pair[0] if pair else None
            result["rankCheck"] = (
                {
                    "rank": check.rank,
                    "found": check.found,
                    "resultLimit": check.result_limit,
                    "status": check.status,
                    "checkedAt": _iso_utc(check.checked_at),
                }
                if check is not None
                else None
            )
        result["country"] = country
        result["device"] = device
        result["keyword"] = keyword
        return result

    def discover_apple_ads_accounts(self, _body: dict[str, Any]) -> dict[str, object]:
        return discover_accounts()

    def select_apple_ads_account(self, body: dict[str, Any]) -> dict[str, object]:
        return select_account(int(body["adAccountId"]))

    def sync_apple_ads(self, body: dict[str, Any]) -> dict[str, object]:
        return sync_apple_ads(
            apple_app_id=int(body["appId"]),
            country=str(body.get("country", "us")),
            device=str(body.get("device", "iphone")),
            days=int(body.get("days", 30)),
        )

    def competitors(self, app_id: int, country: str, device: str) -> dict[str, object]:
        return competitor_matrix(app_id, country, device)

    def add_competitor(self, body: dict[str, Any]) -> dict[str, object]:
        return add_competitor(
            primary_app_id=int(body["appId"]),
            apple_app_id=int(body["competitorAppId"]),
            name=str(body["name"]),
            artwork_url=(str(body["artworkUrl"]) if body.get("artworkUrl") is not None else None),
        )

    def remove_competitor(self, body: dict[str, Any]) -> dict[str, object]:
        return remove_competitor(int(body["competitorAppId"]))

    def refresh_competitor_ranks(self, body: dict[str, Any]) -> dict[str, object]:
        return refresh_competitor_ranks(
            int(body["appId"]),
            str(body.get("country", "us")),
            str(body.get("device", "iphone")),
        )

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
        translator = self._keyword_translator(body.get("provider"))
        return localization_payload(keywords, countries, translator=translator)

    @staticmethod
    def _keyword_translator(provider: object = None) -> Translator:
        """Translate keywords with the configured local AI provider (curated phrases win)."""

        settings = load_settings()
        chosen = str(provider or settings.agent_provider)

        def translate(
            phrases: Sequence[str], languages: Sequence[str]
        ) -> dict[str, dict[str, str]]:
            _provider, translations = generate_keyword_translations(
                keywords=phrases,
                languages=languages,
                provider=chosen,
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
                timeout=settings.agent_timeout,
            )
            return translations

        return translate

    def niche(self, board_id: int | None = None) -> dict[str, object]:
        settings = load_settings()
        with session_scope() as session:
            payload = niche_board_payload(session, board_id)
        payload["providers"] = [
            provider_payload(provider)
            for provider in provider_status(
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
            )
        ]
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
            codex_path=settings.agent_codex_path,
            claude_path=settings.agent_claude_path,
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
        warnings = localize_board_terms(board_id, translator=self._keyword_translator(provider))
        check = refresh_niche_metrics(board_id, settings)
        payload = self.niche(board_id)
        payload["generation"] = {
            "provider": generated.provider,
            "keywords": generated.keywords,
            "check": asdict(check),
            "localizationWarnings": warnings,
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
            codex_path=settings.agent_codex_path,
            claude_path=settings.agent_claude_path,
            timeout=settings.agent_timeout,
        )
        with session_scope() as session:
            board = get_niche_board(session, board_id)
            if board is None:
                raise ValueError(f"unknown niche board: {board_id}")
            added = add_niche_keywords(session, board, generated.keywords)
            added_ids = {item.id for item in added}
        check = None
        if added_ids:
            localize_board_terms(
                board_id, translator=self._keyword_translator(body.get("provider"))
            )
            check = refresh_niche_metrics(board_id, settings, keyword_ids=added_ids)
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
        if added:
            localize_board_terms(
                board_id, translator=self._keyword_translator(), countries={country}
            )
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
        warnings = localize_board_terms(board_id, translator=self._keyword_translator())
        result = refresh_niche_metrics(board_id, settings)
        payload = self.niche(board_id)
        payload["check"] = {**asdict(result), "localizationWarnings": warnings}
        return payload

    def save_listing_coverage(self, body: dict[str, Any]) -> dict[str, object]:
        app_id = int(body["appId"])
        country = validate_country_code(str(body["country"]))
        device = validate_device(str(body.get("device", "iphone")))
        name = " ".join(str(body.get("name", "")).split())
        subtitle = " ".join(str(body.get("subtitle", "")).split())
        keywords = " ".join(str(body.get("keywords", "")).split())
        goal = str(body.get("goal", "aso_seo_aeo")).strip()
        brand_term = " ".join(str(body.get("brandTerm", "")).split())
        if not name:
            raise ValueError("listing name is required")
        if goal not in {"aso_seo_aeo", "ugc_ads"}:
            raise ValueError("goal must be aso_seo_aeo or ugc_ads")
        if not brand_term:
            raise ValueError("brand term is required")
        if len(brand_term) > 255:
            raise ValueError("brand term must be 255 characters or fewer")
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
                channel_goal=goal,
                brand_term=brand_term,
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
            strategy = analyze_distribution_strategy(
                name,
                subtitle,
                keywords,
                goal=goal,
                brand_term=brand_term,
            )
        health: dict[str, object] | None = None
        try:
            listing = self.listing(app_id, country)
            health = assess_listing(listing, strategy=strategy).as_dict()
        except AppleClientError:
            logger.debug(
                "Could not recalculate health after saving listing audit for app %s", app_id
            )
        return {
            "metadata": {
                "name": metadata.name,
                "subtitle": metadata.subtitle,
                "keywords": metadata.keyword_field,
                "channelGoal": metadata.channel_goal,
                "brandTerm": metadata.brand_term,
                "updatedAt": _iso_utc(metadata.updated_at),
            },
            "country": country,
            "device": device,
            "analysis": asdict(analysis),
            "strategy": asdict(strategy),
            "health": health,
        }

    def pricing_items(self, body: dict[str, Any]) -> dict[str, object]:
        return pricing.list_items(int(body["appId"]))

    def pricing_suggest(self, body: dict[str, Any]) -> dict[str, object]:
        """Read prices from App Store Connect and compute PPP suggestions (no writes)."""

        return pricing.suggestions(
            int(body["appId"]),
            kind=str(body["kind"]),
            item_id=str(body["id"]),
            scope="all" if body.get("scope") == "all" else "tracked",
            floor=float(body.get("floor", pricing.DEFAULT_FLOOR)),
            ceiling=float(body.get("ceiling", pricing.DEFAULT_CEILING)),
        )

    def pricing_push(self, body: dict[str, Any]) -> dict[str, object]:
        """Write reviewed price changes (the UI lists and confirms each one first)."""

        licensing.require("price-push")
        changes = body.get("changes")
        return pricing.push_prices(
            int(body["appId"]),
            kind=str(body["kind"]),
            item_id=str(body["id"]),
            item_name=str(body.get("name", "")),
            changes=[item for item in changes if isinstance(item, dict)]
            if isinstance(changes, list)
            else [],
            preserve_current_price=bool(body.get("preserveCurrentPrice", True)),
        )

    def licence_action(self, body: dict[str, Any]) -> dict[str, object]:
        """Activate or remove the Mac app licence (verified offline)."""

        if body.get("remove"):
            licensing.remove()
        else:
            licensing.activate(str(body.get("key", "")))
        return self.desktop_status()

    def desktop_status(self) -> dict[str, object]:
        return {**licensing.status(), "settings": load_desktop_settings()}

    def desktop_settings(self, body: dict[str, Any]) -> dict[str, object]:
        save_desktop_settings(body)
        return self.desktop_status()

    def export_fastlane(self, body: dict[str, Any]) -> dict[str, object]:
        """Write a fastlane metadata folder under the local exports directory only."""

        app_id = int(body["appId"])
        with session_scope() as session:
            app = session.scalar(select(App).where(App.apple_app_id == app_id))
            if app is None:
                raise ValueError(f"unknown app ID: {app_id}")
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            folder = exports_dir() / "fastlane" / str(app.bundle_id or app.apple_app_id) / stamp
            result = export_fastlane_metadata(
                session, app, folder, include_unapproved=bool(body.get("includeUnapproved"))
            )
        return {
            "path": str(result.metadata_dir),
            "locales": result.locales,
            "skipped": result.skipped,
        }

    def reveal_export(self, body: dict[str, Any]) -> dict[str, object]:
        """Show an exported folder in Finder; only paths inside the exports folder."""

        root = exports_dir().resolve()
        target = Path(str(body.get("path", ""))).expanduser().resolve()
        if not target.is_relative_to(root) or not target.exists():
            raise ValueError("only exported folders can be revealed")
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(target)], check=False, timeout=10)
        return {"revealed": str(target)}

    def set_background_sync(self, body: dict[str, Any]) -> dict[str, object]:
        """Turn the daily background rank check (macOS LaunchAgent) on or off."""

        return background_sync.enable() if bool(body.get("enabled")) else background_sync.disable()

    def add_country(self, body: dict[str, Any]) -> dict[str, object]:
        """Add (or reactivate) an App Store storefront from the registry."""

        found = require_market(str(body.get("code", "")))
        with session_scope() as session:
            item, created = add_storefront(session, found.code)
            return {
                "created": created,
                "country": {
                    "code": item.country_code,
                    "name": item.display_name,
                    "active": item.active,
                },
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

    def mark_competitor_brand(self, body: dict[str, Any]) -> dict[str, object]:
        """Mark or unmark a keyword as a competitor's brand for the target's app."""

        target_id = int(body["targetId"])
        competitor = bool(body.get("competitor", True))
        with session_scope() as session:
            target = session.get(TrackingTarget, target_id)
            if target is None:
                raise ValueError(f"unknown tracking target: {target_id}")
            set_competitor_brand(session, target, competitor)
            return {"keyword": target.keyword.keyword, "competitorBrand": competitor}

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
            due_targets, skipped = filter_targets_due_for_check(
                session,
                targets,
                cutoff=datetime.now(UTC) - timedelta(hours=24),
            )
            result = run_checks(session, due_targets, settings)
            pairs = latest_pairs(session, due_targets)
            rankings = self._rankings(
                session,
                [
                    RankingRow(target, pairs[target.id][0], pairs[target.id][1])
                    for target in due_targets
                    if target.id in pairs
                ],
            )
            return {
                "checks": len(result.checks),
                "searches": result.searches,
                "failures": result.failures,
                "rankings": rankings,
                "skipped": skipped,
            }

    @classmethod
    def _rankings(cls, session: Session, rows: list[RankingRow]) -> list[dict[str, object]]:
        measurements = popularity_lookup(session, (_popularity_key(row) for row in rows))
        apple_ads = popularity_configured() if rows else False
        brands = competitor_brand_keys(session, (row.target.app_id for row in rows))
        return [
            cls._ranking(
                row,
                measurements.get(_popularity_key(row)),
                apple_ads=apple_ads,
                competitor_brand=(
                    (row.target.app_id, row.target.keyword.normalized_keyword) in brands
                ),
            )
            for row in rows
        ]

    @staticmethod
    def _ranking(
        row: RankingRow,
        popularity: KeywordPopularity | None = None,
        *,
        apple_ads: bool = False,
        competitor_brand: bool = False,
    ) -> dict[str, object]:
        """``popularityStatus``: Apple's value is "measured", Apple has none ("unavailable"),
        Apple Ads is connected but has not been asked yet ("pending"), or None without
        Apple Ads, the only case where the dashboard falls back to the local estimate.

        ``opportunity``: Apple popularity still to win (see ``popularity_opportunity``),
        None without Apple's value or a difficulty estimate, never from the local estimate.

        ``competitorBrand``: the user marked the keyword as another app's name, which
        App Review keeps out of metadata, so it is an Apple Ads target only."""

        return {
            "targetId": row.target.id,
            "keyword": row.target.keyword.keyword,
            "competitorBrand": competitor_brand,
            "country": row.target.storefront.country_code,
            "device": row.target.device,
            "rank": row.latest.rank,
            "found": row.latest.found,
            "resultLimit": row.latest.result_limit,
            "volumeEstimate": row.latest.estimate.volume if row.latest.estimate else None,
            "popularity": popularity.popularity if popularity else None,
            "popularityStatus": (
                ("pending" if apple_ads else None)
                if popularity is None
                else "measured"
                if popularity.popularity is not None
                else "unavailable"
            ),
            "popularityFetchedAt": _iso_utc(popularity.fetched_at) if popularity else None,
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
                    "averageRating": item.average_rating,
                    "ratingCount": item.rating_count,
                }
                for item in row.latest.top_apps
            ],
            "previousRank": row.previous.rank if row.previous else None,
            "previousFound": row.previous.found if row.previous else None,
            "change": movement(row.latest, row.previous),
            "checkedAt": _iso_utc(row.latest.checked_at),
            "opportunity": popularity_opportunity(
                popularity.popularity if popularity else None,
                row.latest.estimate.difficulty if row.latest.estimate else None,
                rank=row.latest.rank,
                found=row.latest.found,
            ),
            "status": row.latest.status,
            "error": row.latest.error_message,
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
            if parsed.path == "/api/licence":
                self._json(self.service.desktop_status())
                return
            if parsed.path == "/api/pricing":
                query = parse_qs(parsed.query)
                self._json(pricing.pricing_payload(int(query["appId"][0])))
                return
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
            if parsed.path == "/api/competitors":
                query = parse_qs(parsed.query)
                self._json(
                    self.service.competitors(
                        int(query["appId"][0]),
                        query.get("country", ["us"])[0],
                        query.get("device", ["iphone"])[0],
                    )
                )
                return
            if parsed.path == "/api/niche":
                query = parse_qs(parsed.query)
                board_id = int(query["boardId"][0]) if query.get("boardId") else None
                self._json(self.service.niche(board_id))
                return
            if parsed.path == "/api/localization-studio":
                query = parse_qs(parsed.query)
                self._json(
                    self.service.localization_studio(
                        int(query["appId"][0]),
                        query.get("country", ["us"])[0],
                    )
                )
                return
            if parsed.path.startswith("/api/audits"):
                query = parse_qs(parsed.query)
                segments = [item for item in parsed.path.split("/") if item]
                run_id = int(segments[2]) if len(segments) > 2 and segments[2].isdigit() else None
                if run_id is None and query.get("runId"):
                    run_id = int(query["runId"][0])
                app_id = int(query["appId"][0])
                self._json(
                    self.service.audit(
                        app_id,
                        run_id,
                        query.get("country", [None])[0],
                        query.get("device", [None])[0],
                    )
                )
                return
            if parsed.path == "/api/background-sync":
                self._json(background_sync.status())
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
            if parsed.path == "/api/apple-ads":
                query = parse_qs(parsed.query)
                app_id = int(query["appId"][0]) if query.get("appId") else None
                self._json(
                    self.service.apple_ads(
                        app_id,
                        query.get("country", ["us"])[0],
                        query.get("device", ["iphone"])[0],
                    )
                )
                return
            self._static(parsed.path)
        except (
            ValueError,
            KeyError,
            AppleClientError,
            AppleAdsError,
            AppStoreConnectError,
            AgentError,
        ) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            logger.debug("Dashboard GET failed", exc_info=True)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"local dashboard error: {exc}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        rejection = self._cross_origin_rejection()
        if rejection:
            self._error(HTTPStatus.FORBIDDEN, rejection)
            return
        try:
            body = self._read_json()
            actions = {
                "/api/keywords": self.service.add_keyword_targets,
                "/api/keywords/check-rank": self.service.check_paid_keyword_rank,
                "/api/keywords/localize": self.service.localize_keywords,
                "/api/listing-metadata": self.service.save_listing_coverage,
                "/api/apps": self.service.add_app_from_apple,
                "/api/countries": self.service.add_country,
                "/api/background-sync": self.service.set_background_sync,
                "/api/exports/fastlane": self.service.export_fastlane,
                "/api/licence": self.service.licence_action,
                "/api/desktop/settings": self.service.desktop_settings,
                "/api/pricing/items": self.service.pricing_items,
                "/api/pricing/suggest": self.service.pricing_suggest,
                "/api/pricing/push": self.service.pricing_push,
                "/api/reveal": self.service.reveal_export,
                "/api/apps/deactivate": self.service.deactivate_app,
                "/api/check": self.service.check,
                "/api/targets/deactivate": self.service.deactivate_target,
                "/api/targets/competitor-brand": self.service.mark_competitor_brand,
                "/api/onboarding/complete": self.service.finish_onboarding,
                "/api/settings/agent": self.service.save_agent_provider,
                "/api/apple-ads/discover": self.service.discover_apple_ads_accounts,
                "/api/apple-ads/account": self.service.select_apple_ads_account,
                "/api/apple-ads/sync": self.service.sync_apple_ads,
                "/api/competitors/add": self.service.add_competitor,
                "/api/competitors/remove": self.service.remove_competitor,
                "/api/competitors/refresh": self.service.refresh_competitor_ranks,
                "/api/niche/generate": self.service.generate_niche_board,
                "/api/niche/check": self.service.check_niche_board,
                "/api/niche/agent-keywords": self.service.add_niche_agent_keywords,
                "/api/niche/countries/add": self.service.add_niche_market,
                "/api/niche/countries/remove": self.service.remove_niche_market,
                "/api/audits": self.service.start_audit,
                "/api/audits/cancel": self.service.cancel_audit,
                "/api/audits/expand": self.service.expand_audit,
                "/api/agent/test": self.service.test_agent_provider,
                "/api/agent/check": self.service.check_agent_provider,
                "/api/agent/sign-in": self.service.sign_in_agent_provider,
                "/api/app-store-connect/settings": self.service.save_app_store_connect_settings,
                "/api/app-store-connect/test": self.service.test_app_store_connect,
                "/api/localization-studio/main": self.service.set_localization_main_storefront,
                "/api/localization-studio/generate": self.service.generate_localization,
                "/api/localization-studio/approve": self.service.approve_listing_localization,
                "/api/localization-studio/update": self.service.update_listing_localization,
                "/api/localization-studio/push": self.service.push_listing_localization,
            }
            action = actions.get(parsed.path)
            if action is None:
                self._error(HTTPStatus.NOT_FOUND, "unknown local action")
                return
            self._json(action(body))
        except licensing.LicenceRequired as exc:
            self._error(HTTPStatus.PAYMENT_REQUIRED, str(exc))
        except (
            ValueError,
            KeyError,
            AppleClientError,
            AppleAdsError,
            AppStoreConnectError,
            AgentError,
        ) as exc:
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

    def _cross_origin_rejection(self) -> str | None:
        """Refuse actions not sent by this dashboard's own page.

        Actions write files, install a LaunchAgent, and spend Apple quota, so another web
        page open in the same browser must not be able to trigger them. Requires a loopback
        Host (blocks DNS rebinding), a JSON body (a cross-site form can't send one without a
        CORS preflight, which this server never grants), and, when the browser sends an
        Origin, that it matches the Host. Non-browser clients send no Origin.
        """

        host = (self.headers.get("Host") or "").strip().lower()
        hostname = host.rsplit(":", 1)[0].strip("[]") if host else ""
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            return "actions are only accepted on this computer's local address"
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return "actions must be sent as JSON"
        origin = self.headers.get("Origin")
        if origin is not None:
            expected = {f"http://{host}", f"https://{host}"}
            if origin.strip().lower() not in expected:
                return "actions from other web pages are not allowed"
        return None

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


READY_PREFIX = "LOCAL_ASO_READY"


class _ShutdownRequested(Exception):
    """Raised from the SIGTERM handler to leave ``serve_forever`` cleanly."""


def watch_parent(
    parent: int,
    *,
    on_orphaned: Callable[[], None],
    getppid: Callable[[], int] = os.getppid,
    interval: float = 2.0,
    stop: threading.Event | None = None,
) -> None:
    """Call ``on_orphaned`` once the process that started us is gone.

    The Mac app stops the server on Quit, but if the app crashes or is force-quit the
    server would keep running and holding the database; the parent's exit re-parents
    us, which changes ``getppid()``.
    """

    halt = stop or threading.Event()
    while not halt.wait(interval):
        if getppid() != parent:
            on_orphaned()
            return


def serve_dashboard(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    mcp_enabled: bool = True,
    mcp_port: int = 8766,
    open_browser: bool = True,
) -> None:
    """Serve the dashboard until interrupted; bind to loopback by default.

    ``port=0`` binds a free port. Once the socket is listening, one machine-readable
    line ``LOCAL_ASO_READY http://host:port/`` is printed; the desktop app waits for it.
    SIGTERM (sent by the desktop app on quit) stops the server like Ctrl+C.
    """

    from local_aso_tracker.mcp_server import MCPRuntime

    server = LocalDashboardServer((host, port), DashboardHandler)
    bound_port = int(server.server_address[1])
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
    url = f"http://{host}:{bound_port}"
    print(f"Local ASO dashboard: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    print(f"{READY_PREFIX} {url}/", flush=True)
    if open_browser:
        webbrowser.open(url)

    previous_handler: Any = None
    in_main_thread = threading.current_thread() is threading.main_thread()
    if in_main_thread:

        def _on_sigterm(_signum: int, _frame: object) -> None:
            raise _ShutdownRequested

        previous_handler = signal.signal(signal.SIGTERM, _on_sigterm)
    if os.getenv("LOCAL_ASO_DESKTOP") == "1":
        threading.Thread(
            target=watch_parent,
            args=(os.getppid(),),
            kwargs={"on_orphaned": lambda: os.kill(os.getpid(), signal.SIGTERM)},
            daemon=True,
            name="parent-watch",
        ).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except (KeyboardInterrupt, _ShutdownRequested):
        print("\nDashboard stopped.", flush=True)
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous_handler or signal.SIG_DFL)
        DashboardHandler.service.audit_worker.stop()
        sync_worker.stop()
        DashboardHandler.sync_worker = None
        server.server_close()
        if mcp_runtime is not None:
            mcp_runtime.stop()
