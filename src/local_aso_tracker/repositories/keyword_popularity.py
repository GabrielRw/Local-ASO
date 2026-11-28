"""Persistence for Apple Ads keyword popularity measurements."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from local_aso_tracker.models import AppleAdsUnsupportedMarket, KeywordPopularity

PopularityKey = tuple[str, str]


def popularity_lookup(
    session: Session, keys: Iterable[PopularityKey]
) -> dict[PopularityKey, KeywordPopularity]:
    """Return stored measurements keyed by (normalized keyword, upper-case country)."""

    wanted = {(keyword, country.upper()) for keyword, country in keys}
    if not wanted:
        return {}
    rows = session.scalars(
        select(KeywordPopularity).where(
            tuple_(KeywordPopularity.normalized_keyword, KeywordPopularity.country_code).in_(
                list(wanted)
            )
        )
    )
    return {(row.normalized_keyword, row.country_code): row for row in rows}


def store_popularity(
    session: Session,
    *,
    normalized_keyword: str,
    country: str,
    popularity: int | None,
    fetched_at: datetime | None = None,
) -> None:
    """Insert or replace one measurement; ``None`` records that Apple had no value.

    Uses SQLite's upsert so concurrent refreshes (dashboard, CLI, audits) cannot collide.
    """

    values = {
        "normalized_keyword": normalized_keyword,
        "country_code": country.upper(),
        "popularity": popularity,
        "fetched_at": fetched_at or datetime.now(UTC),
    }
    statement = sqlite_insert(KeywordPopularity).values(**values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["normalized_keyword", "country_code"],
            set_={"popularity": popularity, "fetched_at": values["fetched_at"]},
        )
    )


def unsupported_markets(session: Session, *, since: datetime | None = None) -> set[str]:
    """Upper-case storefronts Apple Ads reported it does not serve (checked after ``since``)."""

    statement = select(AppleAdsUnsupportedMarket.country_code)
    if since is not None:
        statement = statement.where(AppleAdsUnsupportedMarket.checked_at >= since)
    return set(session.scalars(statement))


def mark_unsupported_market(
    session: Session, country: str, *, checked_at: datetime | None = None
) -> None:
    when = checked_at or datetime.now(UTC)
    statement = sqlite_insert(AppleAdsUnsupportedMarket).values(
        country_code=country.upper(), checked_at=when
    )
    session.execute(
        statement.on_conflict_do_update(index_elements=["country_code"], set_={"checked_at": when})
    )


def is_stale(row: KeywordPopularity | None, *, cutoff: datetime) -> bool:
    """Whether a measurement is missing or older than ``cutoff``."""

    if row is None:
        return True
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return fetched_at < cutoff
