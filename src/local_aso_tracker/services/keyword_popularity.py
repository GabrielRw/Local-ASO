"""Apple Ads search popularity for tracked keywords.

Apple Ads keyword suggestions carry a popularity score from 5 to 100. Only the
suggestion whose text is the requested keyword itself is that keyword's own score:
other suggestions in the same response are scored relative to the requested term,
so they are discarded. 5 is Apple's floor and means too few searches to tell apart.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.apple.ads import AppleAdsClient, AppleAdsError, AppleAdsSuggestionRecord
from local_aso_tracker.config import load_settings, validate_country_code
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App, AppleAdsAccount, AppleAdsCampaign
from local_aso_tracker.repositories.data import list_targets, normalize_keyword
from local_aso_tracker.repositories.keyword_popularity import (
    is_stale,
    popularity_lookup,
    store_popularity,
)

logger = logging.getLogger(__name__)

POPULARITY_FLOOR = 5
REFRESH_AFTER = timedelta(days=7)
MAX_CONSECUTIVE_FAILURES = 3
# Share of attention assumed captured at rank r is r^-1.2 (1 at #1, 0.15 at #5, 0.06 at #10).
VISIBILITY_RANK_EXPONENT = 1.2
_REFRESH_LOCK = threading.Lock()


@dataclass(frozen=True)
class PopularityRefreshSummary:
    """Outcome of one popularity refresh pass."""

    requested: int
    measured: int
    missing: int
    skipped: int
    failures: int
    unsupported_markets: tuple[str, ...] = ()


@dataclass(frozen=True)
class PopularityReading:
    """A stored Apple Ads measurement: a 5-100 value, or ``None`` when Apple had none."""

    popularity: int | None
    status: str  # "measured" | "unavailable"


def exact_popularity(
    suggestions: Sequence[AppleAdsSuggestionRecord], keyword: str
) -> tuple[bool, int | None]:
    """Return (found, popularity) for the suggestion that is ``keyword`` itself."""

    wanted = normalize_keyword(keyword)
    for suggestion in suggestions:
        try:
            if normalize_keyword(suggestion.text) == wanted:
                return True, suggestion.popularity
        except ValueError:
            continue
    return False, None


def popularity_configured(*, client: AppleAdsClient | None = None) -> bool:
    """Whether an account is selected and a usable local credential exists (no network)."""

    if load_settings().apple_ads_account_id <= 0:
        return False
    status = (client or AppleAdsClient()).credential_status()
    return bool(status.get("available"))


def refresh_keyword_popularity(
    *,
    country: str | None = None,
    force: bool = False,
    client: AppleAdsClient | None = None,
    now: datetime | None = None,
) -> PopularityRefreshSummary:
    """Measure Apple Ads popularity for active tracked keywords that are missing or stale."""

    if not _REFRESH_LOCK.acquire(blocking=False):
        raise ValueError("an Apple Ads popularity refresh is already running")
    try:
        return _refresh(country=country, force=force, client=client, now=now)
    finally:
        _REFRESH_LOCK.release()


def measure_keywords(
    keywords: Sequence[str],
    country: str,
    *,
    client: AppleAdsClient | None = None,
    now: datetime | None = None,
) -> dict[str, PopularityReading]:
    """Return Apple Ads popularity for arbitrary keywords in one market.

    Stored measurements younger than the refresh window are reused. Missing or stale
    keywords are requested only when Apple Ads is configured; any Apple Ads failure is
    logged and the keyword is simply left without a reading. Keys are normalized keywords.
    """

    market = validate_country_code(country).upper()
    terms: dict[tuple[str, str], str] = {}
    for keyword in keywords:
        try:
            terms.setdefault((normalize_keyword(keyword), market), keyword)
        except ValueError:
            continue
    if not terms:
        return {}
    ads_client = client or AppleAdsClient()
    if popularity_configured(client=ads_client):
        try:
            _measure_terms(terms, force=False, client=ads_client, now=now)
        except (AppleAdsError, ValueError) as exc:
            logger.warning("Apple Ads popularity unavailable for %s: %s", market, exc)
    with session_scope() as session:
        stored = popularity_lookup(session, terms)
    return {
        normalized: PopularityReading(
            popularity=row.popularity,
            status="measured" if row.popularity is not None else "unavailable",
        )
        for (normalized, _market), row in stored.items()
    }


def popularity_opportunity(
    popularity: int | None,
    difficulty: int | None,
    *,
    rank: int | None,
    found: bool,
) -> int | None:
    """Apple popularity still to win on a keyword, discounted by its difficulty estimate.

    ``popularity x (100 - difficulty) / 100 x (1 - rank^-1.2)``: 0 at #1, and the full
    discounted popularity when the app is outside the retrieved result window.
    """

    if popularity is None or difficulty is None:
        return None
    captured = rank**-VISIBILITY_RANK_EXPONENT if found and rank and rank > 0 else 0.0
    return round(popularity * (100 - difficulty) / 100 * (1 - captured))


def _refresh(
    *,
    country: str | None,
    force: bool,
    client: AppleAdsClient | None,
    now: datetime | None,
) -> PopularityRefreshSummary:
    storefront = validate_country_code(country) if country else None
    with session_scope() as session:
        targets = list_targets(session, country=storefront, active_only=True)
        terms: dict[tuple[str, str], str] = {}
        for target in targets:
            key = (target.keyword.normalized_keyword, target.storefront.country_code.upper())
            terms.setdefault(key, target.keyword.keyword)
    return _measure_terms(terms, force=force, client=client or AppleAdsClient(), now=now)


def _measure_terms(
    terms: dict[tuple[str, str], str],
    *,
    force: bool,
    client: AppleAdsClient,
    now: datetime | None,
) -> PopularityRefreshSummary:
    account_id = load_settings().apple_ads_account_id
    if account_id <= 0:
        raise ValueError("select an Apple Ads account before measuring keyword popularity")
    current = now or datetime.now(UTC)
    cutoff = current - REFRESH_AFTER
    with session_scope() as session:
        stored = popularity_lookup(session, terms)
        due = [
            (key, text)
            for key, text in sorted(terms.items())
            if force or is_stale(stored.get(key), cutoff=cutoff)
        ]
        promoted_app_id = _stored_promoted_app_id(session, account_id) if due else None

    skipped = len(terms) - len(due)
    if not due:
        return PopularityRefreshSummary(0, 0, 0, skipped, 0)
    if promoted_app_id is None:
        promoted_app_id = _live_promoted_app_id(client, account_id)

    measured = missing = failures = consecutive_failures = 0
    unsupported: set[str] = set()
    for (normalized, market), text in due:
        if market in unsupported:
            continue
        try:
            suggestions = client.keyword_suggestions(
                account_id,
                apple_app_id=promoted_app_id,
                country=market,
                terms=[text],
            )
        except AppleAdsError as exc:
            if _is_unsupported_market(exc):
                # Apple Ads does not serve every App Store storefront; skip the market.
                unsupported.add(market)
                logger.info("Apple Ads does not support storefront %s; skipping it", market)
                continue
            failures += 1
            consecutive_failures += 1
            logger.warning("Apple Ads popularity request failed for one keyword: %s", exc)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                break
            continue
        consecutive_failures = 0
        found, popularity = exact_popularity(suggestions, text)
        if found and popularity is not None:
            measured += 1
        else:
            missing += 1
            popularity = None
        with session_scope() as session:
            store_popularity(
                session,
                normalized_keyword=normalized,
                country=market,
                popularity=popularity,
                fetched_at=current,
            )
    return PopularityRefreshSummary(
        requested=measured + missing + failures,
        measured=measured,
        missing=missing,
        skipped=skipped,
        failures=failures,
        unsupported_markets=tuple(sorted(unsupported)),
    )


def _is_unsupported_market(exc: AppleAdsError) -> bool:
    message = str(exc)
    return "countriesOrRegions" in message and "INVALID_INPUT" in message


def _stored_promoted_app_id(session: Session, account_id: int) -> int | None:
    """Prefer a promoted app that is also tracked locally; any promoted app works."""

    promoted: list[int] = [
        int(app_id)
        for app_id in session.scalars(
            select(AppleAdsCampaign.promoted_object_id)
            .join(AppleAdsAccount, AppleAdsCampaign.ad_account_id == AppleAdsAccount.id)
            .where(
                AppleAdsAccount.ad_account_id == account_id,
                AppleAdsCampaign.promoted_object_id.is_not(None),
                AppleAdsCampaign.deleted.is_(False),
            )
            .distinct()
        )
        if app_id is not None
    ]
    if not promoted:
        return None
    tracked = set(session.scalars(select(App.apple_app_id).where(App.apple_app_id.in_(promoted))))
    return next((app_id for app_id in promoted if app_id in tracked), promoted[0])


def _live_promoted_app_id(client: AppleAdsClient, account_id: int) -> int:
    for campaign in client.campaigns(account_id):
        if campaign.promoted_object_id and not campaign.deleted:
            return campaign.promoted_object_id
    raise ValueError(
        "Apple Ads popularity needs at least one app promoted by a campaign in the selected account"
    )
