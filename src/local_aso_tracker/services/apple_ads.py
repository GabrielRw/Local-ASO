"""Read-only Apple Ads synchronization and dashboard composition."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from local_aso_tracker.apple.ads import AppleAdsClient, AppleAdsSuggestionRecord
from local_aso_tracker.config import (
    load_settings,
    update_settings,
    validate_country_code,
    validate_device,
)
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App
from local_aso_tracker.repositories.apple_ads import (
    apple_ads_payload,
    replace_campaigns,
    replace_keywords,
    replace_metrics,
    replace_suggestions,
    touch_account,
    tracked_suggestion_terms,
    upsert_account,
)

_SYNC_LOCK = threading.Lock()


def apple_ads_status(
    apple_app_id: int | None,
    country: str,
    device: str,
    *,
    client: AppleAdsClient | None = None,
) -> dict[str, object]:
    """Load cached Apple Ads data without making an external request."""

    ads_client = client or AppleAdsClient()
    settings = load_settings()
    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    start, end = _report_window(30)
    with session_scope() as session:
        payload = apple_ads_payload(
            session,
            apple_app_id=apple_app_id,
            country=storefront,
            device=normalized_device,
            selected_account_id=settings.apple_ads_account_id,
            days=30,
            start=start,
            end=end,
        )
    payload["credentials"] = ads_client.credential_status()
    return payload


def discover_accounts(*, client: AppleAdsClient | None = None) -> dict[str, object]:
    """Discover Apple Ads accounts without mutating any campaign."""

    ads_client = client or AppleAdsClient()
    records = ads_client.accounts()
    with session_scope() as session:
        for record in records:
            upsert_account(session, record)
    settings = load_settings()
    return {
        "accounts": [
            {
                "id": item.ad_account_id,
                "orgId": item.org_id,
                "name": item.name,
                "roles": list(item.roles),
            }
            for item in records
        ],
        "selectedAccountId": settings.apple_ads_account_id,
    }


def select_account(
    ad_account_id: int, *, client: AppleAdsClient | None = None
) -> dict[str, object]:
    """Persist one discovered Apple Ads ad account selection."""

    if ad_account_id <= 0:
        raise ValueError("ad account ID must be positive")
    ads_client = client or AppleAdsClient()
    records = ads_client.accounts()
    selected = next((item for item in records if item.ad_account_id == ad_account_id), None)
    if selected is None:
        raise ValueError(f"Apple Ads account is not accessible: {ad_account_id}")
    with session_scope() as session:
        for record in records:
            upsert_account(session, record)
    settings = update_settings(apple_ads_account_id=ad_account_id)
    return {
        "account": {
            "id": selected.ad_account_id,
            "orgId": selected.org_id,
            "name": selected.name,
            "roles": list(selected.roles),
        },
        "selectedAccountId": settings.apple_ads_account_id,
    }


def sync_apple_ads(
    *,
    apple_app_id: int,
    country: str,
    device: str,
    days: int = 30,
    client: AppleAdsClient | None = None,
) -> dict[str, object]:
    """Import campaign, keyword, spend, and suggestion data for one app."""

    if not _SYNC_LOCK.acquire(blocking=False):
        raise ValueError("an Apple Ads synchronization is already running")
    try:
        return _sync_apple_ads(
            apple_app_id=apple_app_id,
            country=country,
            device=device,
            days=days,
            client=client,
        )
    finally:
        _SYNC_LOCK.release()


def _sync_apple_ads(
    *,
    apple_app_id: int,
    country: str,
    device: str,
    days: int,
    client: AppleAdsClient | None,
) -> dict[str, object]:
    if days < 1 or days > 90:
        raise ValueError("Apple Ads report window must be between 1 and 90 days")
    settings = load_settings()
    account_id = settings.apple_ads_account_id
    if account_id <= 0:
        raise ValueError("select an Apple Ads account before syncing")
    storefront = validate_country_code(country)
    normalized_device = validate_device(device)
    ads_client = client or AppleAdsClient()
    started_at = datetime.now(UTC)
    records = ads_client.accounts()
    selected = next((item for item in records if item.ad_account_id == account_id), None)
    if selected is None:
        raise ValueError(f"Apple Ads account is not accessible: {account_id}")

    campaigns = ads_client.campaigns(account_id)
    keywords = ads_client.keywords(account_id, campaigns)
    start, end = _report_window(days)
    metrics = ads_client.keyword_metrics(account_id, campaigns, start=start, end=end)

    with session_scope() as session:
        terms = tracked_suggestion_terms(
            session,
            apple_app_id=apple_app_id,
            country=storefront,
            device=normalized_device,
            limit=20,
        )
    suggestions_by_text: dict[str, AppleAdsSuggestionRecord] = {}
    for seed in terms:
        for suggestion in ads_client.keyword_suggestions(
            account_id,
            apple_app_id=apple_app_id,
            country=storefront,
            terms=[seed],
        ):
            current = suggestions_by_text.get(suggestion.text.casefold())
            if current is None or (suggestion.popularity or 0) > (current.popularity or 0):
                suggestions_by_text[suggestion.text.casefold()] = suggestion
    suggestions = sorted(
        suggestions_by_text.values(),
        key=lambda item: (-(item.popularity or 0), item.text.casefold()),
    )

    with session_scope() as session:
        for record in records:
            upsert_account(session, record)
        account = upsert_account(session, selected)
        campaign_map = replace_campaigns(session, account, campaigns)
        keyword_map = replace_keywords(session, campaign_map, keywords)
        metric_count = replace_metrics(
            session,
            account,
            keyword_map,
            metrics,
            start=start,
            end=end,
        )
        app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        if app is not None:
            replace_suggestions(session, app, storefront, suggestions)
        touch_account(session, account)

    payload = apple_ads_status(
        apple_app_id,
        storefront,
        normalized_device,
        client=ads_client,
    )
    payload["sync"] = {
        "startedAt": started_at.isoformat(),
        "finishedAt": datetime.now(UTC).isoformat(),
        "campaigns": len(campaigns),
        "keywords": len(keywords),
        "metricRows": metric_count,
        "suggestions": len(suggestions),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    return payload


def _report_window(days: int) -> tuple[date, date]:
    end = datetime.now(UTC).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start, end
