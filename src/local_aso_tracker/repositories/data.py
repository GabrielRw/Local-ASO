"""Straightforward SQLAlchemy operations for tracker data."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.config import validate_country_code, validate_device
from local_aso_tracker.models import (
    App,
    AppArtwork,
    Keyword,
    ListingMetadata,
    RankCheck,
    Storefront,
    TrackingTarget,
)

INITIAL_COUNTRIES = {
    "us": "United States",
    "fr": "France",
    "gb": "United Kingdom",
    "ca": "Canada",
    "au": "Australia",
}
INITIAL_KEYWORDS = [
    "astrology",
    "learn astrology",
    "astrology lessons",
    "astrology course",
    "astrology for beginners",
    "birth chart",
    "natal chart",
    "birth chart interpretation",
    "astrology quiz",
    "astrology app",
    "zodiac signs",
    "astrology aspects",
    "astrology houses",
    "planets astrology",
    "astrology learning",
]


def normalize_keyword(value: str) -> str:
    """Trim, collapse whitespace, and case-normalize a keyword."""

    normalized = " ".join(value.split()).casefold()
    if not normalized:
        raise ValueError("keyword cannot be blank")
    if len(normalized) > 255:
        raise ValueError("keyword must be 255 characters or fewer")
    return normalized


def add_app(
    session: Session,
    name: str,
    apple_id: int,
    bundle_id: str | None = None,
    artwork_url: str | None = None,
) -> tuple[App, bool]:
    existing = session.scalar(select(App).where(App.apple_app_id == apple_id))
    if existing:
        existing.active = True
        if artwork_url:
            artwork = session.get(AppArtwork, existing.id)
            if artwork is None:
                session.add(AppArtwork(app_id=existing.id, artwork_url=artwork_url))
            else:
                artwork.artwork_url = artwork_url
        return existing, False
    item = App(
        name=name.strip(),
        apple_app_id=apple_id,
        bundle_id=bundle_id,
    )
    session.add(item)
    session.flush()
    if artwork_url:
        session.add(AppArtwork(app_id=item.id, artwork_url=artwork_url))
    return item, True


def add_keyword(session: Session, value: str) -> tuple[Keyword, bool]:
    normalized = normalize_keyword(value)
    existing = session.scalar(select(Keyword).where(Keyword.normalized_keyword == normalized))
    if existing:
        existing.active = True
        return existing, False
    item = Keyword(keyword=" ".join(value.split()), normalized_keyword=normalized)
    session.add(item)
    session.flush()
    return item, True


def add_storefront(session: Session, code: str, name: str) -> tuple[Storefront, bool]:
    normalized = validate_country_code(code)
    existing = session.scalar(select(Storefront).where(Storefront.country_code == normalized))
    if existing:
        return existing, False
    item = Storefront(country_code=normalized, display_name=name.strip())
    session.add(item)
    session.flush()
    return item, True


def seed_catalog(session: Session) -> dict[str, int]:
    """Idempotently create the AstroLingo app, countries, and keywords."""

    counts = {"apps": 0, "countries": 0, "keywords": 0}
    _, created = add_app(session, "AstroLingo", 6771773264)
    counts["apps"] += int(created)
    for code, name in INITIAL_COUNTRIES.items():
        _, created = add_storefront(session, code, name)
        counts["countries"] += int(created)
    for keyword in INITIAL_KEYWORDS:
        _, created = add_keyword(session, keyword)
        counts["keywords"] += int(created)
    return counts


def resolve_entities(
    session: Session, apple_id: int, keyword: str, country: str
) -> tuple[App, Keyword, Storefront]:
    app = session.scalar(select(App).where(App.apple_app_id == apple_id))
    key = session.scalar(
        select(Keyword).where(Keyword.normalized_keyword == normalize_keyword(keyword))
    )
    store = session.scalar(
        select(Storefront).where(Storefront.country_code == validate_country_code(country))
    )
    if app is None:
        raise ValueError(f"unknown app ID: {apple_id}")
    if key is None:
        raise ValueError(f"unknown keyword: {keyword}")
    if store is None:
        raise ValueError(f"unknown country: {country}")
    return app, key, store


def add_target(
    session: Session,
    apple_id: int,
    keyword: str,
    country: str,
    device: str = "iphone",
) -> tuple[TrackingTarget, bool]:
    app, key, store = resolve_entities(session, apple_id, keyword, country)
    normalized_device = validate_device(device)
    existing = session.scalar(
        select(TrackingTarget).where(
            TrackingTarget.app_id == app.id,
            TrackingTarget.keyword_id == key.id,
            TrackingTarget.storefront_id == store.id,
            TrackingTarget.device == normalized_device,
        )
    )
    if existing:
        if not existing.active:
            existing.active = True
        return existing, False
    target = TrackingTarget(app=app, keyword=key, storefront=store, device=normalized_device)
    session.add(target)
    session.flush()
    return target, True


def seed_targets(session: Session, apple_id: int = 6771773264) -> int:
    """Create the cross-product of the app and active seeded catalog."""

    app = session.scalar(select(App).where(App.apple_app_id == apple_id, App.active.is_(True)))
    if app is None:
        raise ValueError(f"active app {apple_id} is not configured; run 'aso init --seed'")
    keywords = session.scalars(select(Keyword).where(Keyword.active.is_(True))).all()
    countries = session.scalars(select(Storefront).where(Storefront.active.is_(True))).all()
    created = 0
    for key in keywords:
        for country in countries:
            _, was_created = add_target(session, apple_id, key.keyword, country.country_code)
            created += int(was_created)
    return created


def get_listing_metadata(
    session: Session,
    apple_id: int,
    country: str,
) -> ListingMetadata | None:
    """Return saved metadata for one app and storefront."""

    storefront = session.scalar(
        select(Storefront).where(Storefront.country_code == validate_country_code(country))
    )
    app = session.scalar(select(App).where(App.apple_app_id == apple_id))
    if app is None or storefront is None:
        return None
    return session.scalar(
        select(ListingMetadata).where(
            ListingMetadata.app_id == app.id,
            ListingMetadata.storefront_id == storefront.id,
        )
    )


def save_listing_metadata(
    session: Session,
    apple_id: int,
    country: str,
    *,
    name: str,
    subtitle: str,
    keyword_field: str,
) -> ListingMetadata:
    """Create or update the user-provided metadata for one app/storefront."""

    app = session.scalar(select(App).where(App.apple_app_id == apple_id))
    storefront = session.scalar(
        select(Storefront).where(Storefront.country_code == validate_country_code(country))
    )
    if app is None:
        raise ValueError(f"unknown app ID: {apple_id}")
    if storefront is None:
        raise ValueError(f"unknown country: {country}")
    item = session.scalar(
        select(ListingMetadata).where(
            ListingMetadata.app_id == app.id,
            ListingMetadata.storefront_id == storefront.id,
        )
    )
    if item is None:
        item = ListingMetadata(
            app_id=app.id,
            storefront_id=storefront.id,
            name=name,
            subtitle=subtitle,
            keyword_field=keyword_field,
        )
        session.add(item)
    else:
        item.name = name
        item.subtitle = subtitle
        item.keyword_field = keyword_field
        item.updated_at = datetime.now(UTC)
    session.flush()
    return item


def target_query(
    *,
    apple_id: int | None = None,
    country: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    active_only: bool = False,
) -> Select[tuple[TrackingTarget]]:
    query = select(TrackingTarget).options(
        selectinload(TrackingTarget.app),
        selectinload(TrackingTarget.keyword),
        selectinload(TrackingTarget.storefront),
    )
    if active_only:
        query = (
            query.join(TrackingTarget.app)
            .join(TrackingTarget.keyword)
            .join(TrackingTarget.storefront)
        )
        query = query.where(
            TrackingTarget.active.is_(True),
            App.active.is_(True),
            Keyword.active.is_(True),
            Storefront.active.is_(True),
        )
    if apple_id is not None:
        query = query.where(TrackingTarget.app.has(apple_app_id=apple_id))
    if country is not None:
        query = query.where(
            TrackingTarget.storefront.has(country_code=validate_country_code(country))
        )
    if keyword is not None:
        query = query.where(
            TrackingTarget.keyword.has(normalized_keyword=normalize_keyword(keyword))
        )
    if device is not None:
        query = query.where(TrackingTarget.device == validate_device(device))
    return query.order_by(TrackingTarget.id)


def list_targets(
    session: Session,
    *,
    apple_id: int | None = None,
    country: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    active_only: bool = False,
) -> list[TrackingTarget]:
    return list(
        session.scalars(
            target_query(
                apple_id=apple_id,
                country=country,
                keyword=keyword,
                device=device,
                active_only=active_only,
            )
        ).all()
    )


def filter_missing_today(session: Session, targets: list[TrackingTarget]) -> list[TrackingTarget]:
    """Remove targets with any check during the current local calendar day."""

    local_tz = datetime.now().astimezone().tzinfo
    local_start = datetime.combine(date.today(), time.min, tzinfo=local_tz)
    utc_start = local_start.astimezone(UTC)
    checked_ids = (
        set(
            session.scalars(
                select(RankCheck.tracking_target_id).where(
                    RankCheck.tracking_target_id.in_([item.id for item in targets]),
                    RankCheck.checked_at >= utc_start,
                )
            ).all()
        )
        if targets
        else set()
    )
    return [item for item in targets if item.id not in checked_ids]


def successful_checks(
    session: Session,
    targets: list[TrackingTarget],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[RankCheck]:
    ids = [target.id for target in targets]
    if not ids:
        return []
    query = (
        select(RankCheck)
        .options(selectinload(RankCheck.estimate), selectinload(RankCheck.top_apps))
        .where(RankCheck.tracking_target_id.in_(ids), RankCheck.status == "success")
    )
    if start is not None:
        query = query.where(RankCheck.checked_at >= start)
    if end is not None:
        query = query.where(RankCheck.checked_at <= end)
    return list(session.scalars(query.order_by(RankCheck.checked_at, RankCheck.id)).all())


def latest_pairs(
    session: Session, targets: list[TrackingTarget]
) -> dict[int, tuple[RankCheck, RankCheck | None]]:
    """Return latest and previous successful check for each target."""

    checks = successful_checks(session, targets)
    grouped: dict[int, list[RankCheck]] = {}
    for check in checks:
        grouped.setdefault(check.tracking_target_id, []).append(check)
    return {
        target_id: (items[-1], items[-2] if len(items) > 1 else None)
        for target_id, items in grouped.items()
    }


def parse_date_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def count_checks(session: Session) -> int:
    return session.scalar(select(func.count(RankCheck.id))) or 0
