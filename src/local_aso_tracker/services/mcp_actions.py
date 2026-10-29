"""Validated write actions exposed by the local MCP server."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from local_aso_tracker.apple.listing import lookup_listing
from local_aso_tracker.config import load_settings, validate_country_code, validate_device
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App, Keyword, Storefront, TrackingTarget
from local_aso_tracker.repositories.data import (
    add_app as add_app_record,
)
from local_aso_tracker.repositories.data import (
    add_keyword,
    add_target,
    filter_targets_due_for_check,
    list_targets,
    normalize_keyword,
)
from local_aso_tracker.services.checks import run_checks

MAX_KEYWORDS_PER_CALL = 50
MAX_COUNTRIES_PER_CALL = 31
MAX_CHECK_SEARCHES_PER_CALL = 50


def add_app(apple_app_id: int, country: str = "us") -> dict[str, object]:
    """Add or restore one app using Apple's public lookup data."""

    if apple_app_id <= 0:
        raise ValueError("apple_app_id must be a positive integer")
    storefront = validate_country_code(country)
    with session_scope() as session:
        store = session.scalar(
            select(Storefront).where(
                Storefront.country_code == storefront,
                Storefront.active.is_(True),
            )
        )
        if store is None:
            raise ValueError(f"inactive or unknown country: {storefront}")
        previous = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        was_active = previous.active if previous is not None else False
    settings = load_settings()
    listing = lookup_listing(
        apple_app_id,
        storefront,
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
    )
    with session_scope() as session:
        app, created = add_app_record(
            session,
            listing.track_name,
            apple_app_id,
            listing.bundle_id,
            listing.artwork_url,
        )
        return {
            "app": {
                "name": app.name,
                "appleAppId": app.apple_app_id,
                "bundleId": app.bundle_id,
                "active": app.active,
            },
            "country": storefront,
            "created": created,
            "restored": not created and not was_active,
        }


def add_keywords(
    apple_app_id: int,
    keywords: Sequence[str],
    countries: Sequence[str],
    *,
    devices: Sequence[str] = ("iphone",),
    check_now: bool = True,
) -> dict[str, object]:
    """Create tracking targets and optionally fetch their first public ranks."""

    cleaned_keywords = _clean_keywords(keywords)
    cleaned_countries = _clean_countries(countries)
    cleaned_devices = _clean_devices(devices)
    combinations = len(cleaned_keywords) * len(cleaned_countries) * len(cleaned_devices)
    if check_now and combinations > MAX_CHECK_SEARCHES_PER_CALL:
        raise ValueError(
            f"check_now would require {combinations} Apple searches; "
            f"the limit is {MAX_CHECK_SEARCHES_PER_CALL}. Split the request or set check_now=false."
        )

    settings = load_settings()
    with session_scope() as session:
        app = session.scalar(
            select(App).where(
                App.apple_app_id == apple_app_id,
                App.active.is_(True),
            )
        )
        if app is None:
            raise ValueError(f"active app not found: {apple_app_id}")
        storefronts = {
            item.country_code: item
            for item in session.scalars(
                select(Storefront).where(
                    Storefront.country_code.in_(cleaned_countries),
                    Storefront.active.is_(True),
                )
            )
        }
        missing = [country for country in cleaned_countries if country not in storefronts]
        if missing:
            raise ValueError(f"inactive or unknown country: {missing[0]}")

        keyword_items: dict[int, Keyword] = {}
        keywords_created = 0
        targets_created = 0
        targets_reactivated = 0
        targets_to_check: dict[int, TrackingTarget] = {}
        for keyword_text in cleaned_keywords:
            keyword, keyword_created = add_keyword(session, keyword_text)
            keyword_items.setdefault(keyword.id, keyword)
            keywords_created += int(keyword_created)
            for country in cleaned_countries:
                store = storefronts[country]
                for device in cleaned_devices:
                    existing = session.scalar(
                        select(TrackingTarget).where(
                            TrackingTarget.app_id == app.id,
                            TrackingTarget.keyword_id == keyword.id,
                            TrackingTarget.storefront_id == store.id,
                            TrackingTarget.device == device,
                        )
                    )
                    was_inactive = existing is not None and not existing.active
                    target, created = add_target(
                        session,
                        apple_app_id,
                        keyword.keyword,
                        country,
                        device,
                    )
                    targets_created += int(created)
                    targets_reactivated += int(was_inactive)
                    targets_to_check[target.id] = target

        check = (
            run_checks(session, list(targets_to_check.values()), settings) if check_now else None
        )
        return {
            "app": {"name": app.name, "appleAppId": app.apple_app_id},
            "keywords": [item.keyword for item in keyword_items.values()],
            "countries": cleaned_countries,
            "devices": cleaned_devices,
            "keywordsCreated": keywords_created,
            "targetsCreated": targets_created,
            "targetsReactivated": targets_reactivated,
            "targetsUnchanged": combinations - targets_created - targets_reactivated,
            "check": (
                {
                    "checks": len(check.checks),
                    "searches": check.searches,
                    "failures": check.failures,
                }
                if check is not None
                else None
            ),
        }


def run_rank_checks(
    *,
    apple_app_id: int | None = None,
    countries: Sequence[str] | None = None,
    devices: Sequence[str] | None = None,
    keyword: str | None = None,
) -> dict[str, object]:
    """Run public Apple checks for a bounded active-target selection."""

    cleaned_countries = set(_clean_countries(countries)) if countries else None
    cleaned_devices = set(_clean_devices(devices)) if devices else None
    normalized_keyword = normalize_keyword(keyword) if keyword else None
    settings = load_settings()
    with session_scope() as session:
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            active_only=True,
        )
        selected = [
            target
            for target in targets
            if (cleaned_countries is None or target.storefront.country_code in cleaned_countries)
            and (cleaned_devices is None or target.device in cleaned_devices)
            and (
                normalized_keyword is None
                or target.keyword.normalized_keyword == normalized_keyword
            )
        ]
        searches = len(
            {
                (target.keyword.normalized_keyword, target.storefront.country_code, target.device)
                for target in selected
            }
        )
        if searches > MAX_CHECK_SEARCHES_PER_CALL:
            raise ValueError(
                f"selection requires {searches} Apple searches; "
                f"the limit is {MAX_CHECK_SEARCHES_PER_CALL}. Use narrower filters."
            )
        due_targets, skipped = filter_targets_due_for_check(
            session,
            selected,
            cutoff=datetime.now(UTC) - timedelta(hours=24),
        )
        result = run_checks(session, due_targets, settings)
        return {
            "checks": len(result.checks),
            "searches": result.searches,
            "failures": result.failures,
            "targetsSelected": len(selected),
            "targetsSkipped": skipped,
        }


def stop_tracking_keywords(
    apple_app_id: int,
    keywords: Sequence[str],
    *,
    countries: Sequence[str] | None = None,
    devices: Sequence[str] | None = None,
) -> dict[str, object]:
    """Deactivate matching targets without deleting their ranking history."""

    cleaned_keywords = {normalize_keyword(keyword) for keyword in _clean_keywords(keywords)}
    cleaned_countries = set(_clean_countries(countries)) if countries else None
    cleaned_devices = set(_clean_devices(devices)) if devices else None
    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {apple_app_id}")
        targets = list_targets(
            session,
            apple_id=apple_app_id,
            active_only=True,
        )
        selected = [
            target
            for target in targets
            if target.keyword.normalized_keyword in cleaned_keywords
            and (cleaned_countries is None or target.storefront.country_code in cleaned_countries)
            and (cleaned_devices is None or target.device in cleaned_devices)
        ]
        for target in selected:
            target.active = False
        return {
            "app": {"name": app.name, "appleAppId": app.apple_app_id},
            "deactivated": len(selected),
            "targets": [
                {
                    "keyword": target.keyword.keyword,
                    "country": target.storefront.country_code,
                    "device": target.device,
                }
                for target in selected
            ],
        }


def _clean_keywords(values: Sequence[str]) -> list[str]:
    if not values:
        raise ValueError("at least one keyword is required")
    if len(values) > MAX_KEYWORDS_PER_CALL:
        raise ValueError(f"at most {MAX_KEYWORDS_PER_CALL} keywords can be added per call")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = " ".join(str(value).split())
        normalized = normalize_keyword(keyword)
        if normalized not in seen:
            cleaned.append(keyword)
            seen.add(normalized)
    return cleaned


def _clean_countries(values: Sequence[str]) -> list[str]:
    if not values:
        raise ValueError("at least one country is required")
    if len(values) > MAX_COUNTRIES_PER_CALL:
        raise ValueError(f"at most {MAX_COUNTRIES_PER_CALL} countries can be selected per call")
    return list(dict.fromkeys(validate_country_code(value) for value in values))


def _clean_devices(values: Sequence[str]) -> list[str]:
    if not values:
        raise ValueError("at least one device is required")
    return list(dict.fromkeys(validate_device(value) for value in values))
