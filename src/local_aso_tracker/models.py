"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Date as SADate,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative model base."""


class DashboardOnboarding(Base):
    """Local first-run setup completion, shared by all dashboard browsers."""

    __tablename__ = "dashboard_onboarding"
    __table_args__ = (CheckConstraint("id = 1", name="ck_dashboard_onboarding_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ListingMetadata(Base):
    """User-provided localized metadata used by the coverage audit."""

    __tablename__ = "listing_metadata"
    __table_args__ = (
        UniqueConstraint("app_id", "storefront_id", name="uq_listing_metadata_app_storefront"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    storefront_id: Mapped[int] = mapped_column(
        ForeignKey("storefronts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    keyword_field: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class NicheBoard(Base):
    """An app-independent keyword research board."""

    __tablename__ = "niche_boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    brief: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    keywords: Mapped[list[NicheKeyword]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )
    markets: Mapped[list[NicheMarket]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class NicheKeyword(Base):
    """A keyword in a niche research board."""

    __tablename__ = "niche_keywords"
    __table_args__ = (UniqueConstraint("board_id", "normalized_keyword", name="uq_niche_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("niche_boards.id", ondelete="CASCADE"), index=True
    )
    keyword: Mapped[str] = mapped_column(String(255))
    normalized_keyword: Mapped[str] = mapped_column(String(255), index=True)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    board: Mapped[NicheBoard] = relationship(back_populates="keywords")
    metrics: Mapped[list[NicheMetric]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )


class NicheMarket(Base):
    """A country column in a niche research board."""

    __tablename__ = "niche_markets"
    __table_args__ = (UniqueConstraint("board_id", "country_code", name="uq_niche_market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("niche_boards.id", ondelete="CASCADE"), index=True
    )
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    position: Mapped[int] = mapped_column(Integer)

    board: Mapped[NicheBoard] = relationship(back_populates="markets")


class NicheMetric(Base):
    """Latest Apple-public-data estimate for a board keyword and country."""

    __tablename__ = "niche_metrics"
    __table_args__ = (
        UniqueConstraint("niche_keyword_id", "country_code", name="uq_niche_metric"),
        CheckConstraint(
            "volume_estimate IS NULL OR volume_estimate BETWEEN 0 AND 100",
            name="ck_niche_metrics_volume",
        ),
        CheckConstraint(
            "difficulty_estimate IS NULL OR difficulty_estimate BETWEEN 0 AND 100",
            name="ck_niche_metrics_difficulty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    niche_keyword_id: Mapped[int] = mapped_column(
        ForeignKey("niche_keywords.id", ondelete="CASCADE"), index=True
    )
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    device: Mapped[str] = mapped_column(String(10), default="iphone")
    volume_estimate: Mapped[int | None] = mapped_column(Integer)
    difficulty_estimate: Mapped[int | None] = mapped_column(Integer)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)

    keyword: Mapped[NicheKeyword] = relationship(back_populates="metrics")


class App(Base):
    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    apple_app_id: Mapped[int] = mapped_column(unique=True, index=True)
    bundle_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    targets: Mapped[list[TrackingTarget]] = relationship(back_populates="app")


class AppArtwork(Base):
    """Public artwork kept separate from app identity and tracking data."""

    __tablename__ = "app_artwork"

    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    artwork_url: Mapped[str] = mapped_column(Text)


class Storefront(Base):
    __tablename__ = "storefronts"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    targets: Mapped[list[TrackingTarget]] = relationship(back_populates="storefront")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255))
    normalized_keyword: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    targets: Mapped[list[TrackingTarget]] = relationship(back_populates="keyword")


class TrackingTarget(Base):
    __tablename__ = "tracking_targets"
    __table_args__ = (
        UniqueConstraint(
            "app_id", "keyword_id", "storefront_id", "device", name="uq_tracking_target"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), index=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), index=True)
    storefront_id: Mapped[int] = mapped_column(ForeignKey("storefronts.id"), index=True)
    device: Mapped[str] = mapped_column(String(10), default="iphone", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    app: Mapped[App] = relationship(back_populates="targets")
    keyword: Mapped[Keyword] = relationship(back_populates="targets")
    storefront: Mapped[Storefront] = relationship(back_populates="targets")
    checks: Mapped[list[RankCheck]] = relationship(back_populates="tracking_target")


class RankCheck(Base):
    __tablename__ = "rank_checks"
    __table_args__ = (Index("ix_rank_checks_target_checked", "tracking_target_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_target_id: Mapped[int] = mapped_column(ForeignKey("tracking_targets.id"))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    found: Mapped[bool] = mapped_column(Boolean)
    result_limit: Mapped[int] = mapped_column(Integer)
    total_results_reported: Mapped[int | None] = mapped_column(Integer)
    app_name_returned: Mapped[str | None] = mapped_column(String(255))
    app_version_returned: Mapped[str | None] = mapped_column(String(100))
    app_store_url: Mapped[str | None] = mapped_column(Text)
    raw_response_hash: Mapped[str | None] = mapped_column(String(64))
    response_time_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    tracking_target: Mapped[TrackingTarget] = relationship(back_populates="checks")
    estimate: Mapped[RankEstimate | None] = relationship(
        back_populates="rank_check", uselist=False, cascade="all, delete-orphan"
    )
    top_apps: Mapped[list[RankTopApp]] = relationship(
        back_populates="rank_check",
        order_by="RankTopApp.position",
        cascade="all, delete-orphan",
    )


class RankEstimate(Base):
    """A versioned derived score kept separate from Apple's rank evidence."""

    __tablename__ = "rank_estimates"
    __table_args__ = (
        CheckConstraint(
            "volume IS NULL OR volume BETWEEN 0 AND 100",
            name="ck_rank_estimates_volume",
        ),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 0 AND 100",
            name="ck_rank_estimates_difficulty",
        ),
        CheckConstraint(
            "sample_size BETWEEN 0 AND 10",
            name="ck_rank_estimates_sample_size",
        ),
    )

    rank_check_id: Mapped[int] = mapped_column(
        ForeignKey("rank_checks.id", ondelete="CASCADE"), primary_key=True
    )
    volume: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    sample_size: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(50))

    rank_check: Mapped[RankCheck] = relationship(back_populates="estimate")


class RankTopApp(Base):
    """One of the first five app results supporting a stored rank check."""

    __tablename__ = "rank_top_apps"
    __table_args__ = (
        CheckConstraint(
            "position BETWEEN 1 AND 5",
            name="ck_rank_top_apps_position",
        ),
    )

    rank_check_id: Mapped[int] = mapped_column(
        ForeignKey("rank_checks.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    artwork_url: Mapped[str | None] = mapped_column(Text)

    rank_check: Mapped[RankCheck] = relationship(back_populates="top_apps")


class AppleAdsAccount(Base):
    """An Apple Ads ad account visible to the local API credential."""

    __tablename__ = "apple_ads_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ad_account_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    org_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    roles: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AppleAdsCampaign(Base):
    """A read-only Apple Ads campaign linked to its promoted App Store app."""

    __tablename__ = "apple_ads_campaigns"
    __table_args__ = (
        UniqueConstraint("ad_account_id", "campaign_id", name="uq_apple_ads_campaign"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ad_account_id: Mapped[int] = mapped_column(
        ForeignKey("apple_ads_accounts.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    promoted_object_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    promoted_object_type: Mapped[str | None] = mapped_column(String(40))
    countries: Mapped[str] = mapped_column(Text, default="")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    account: Mapped[AppleAdsAccount] = relationship()
    keywords: Mapped[list[AppleAdsKeyword]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class AppleAdsKeyword(Base):
    """An Apple Ads targeting keyword and its current configured bid."""

    __tablename__ = "apple_ads_keywords"
    __table_args__ = (UniqueConstraint("campaign_id", "keyword_id", name="uq_apple_ads_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("apple_ads_campaigns.id", ondelete="CASCADE"), index=True
    )
    keyword_id: Mapped[int] = mapped_column(BigInteger, index=True)
    ad_group_id: Mapped[int | None] = mapped_column(BigInteger)
    ad_group_name: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(String(255))
    normalized_text: Mapped[str] = mapped_column(String(255), index=True)
    match_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    display_status: Mapped[str | None] = mapped_column(String(30))
    bid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    bid_currency: Mapped[str | None] = mapped_column(String(3))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    campaign: Mapped[AppleAdsCampaign] = relationship(back_populates="keywords")
    metrics: Mapped[list[AppleAdsKeywordMetric]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )


class AppleAdsKeywordMetric(Base):
    """Apple Ads keyword performance for one day, market, and device."""

    __tablename__ = "apple_ads_keyword_metrics"
    __table_args__ = (
        UniqueConstraint(
            "apple_ads_keyword_id",
            "metric_date",
            "country_or_region",
            "device_class",
            name="uq_apple_ads_keyword_metric",
        ),
        Index("ix_apple_ads_metrics_account_date", "ad_account_id", "metric_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ad_account_id: Mapped[int] = mapped_column(
        ForeignKey("apple_ads_accounts.id", ondelete="CASCADE"), index=True
    )
    apple_ads_keyword_id: Mapped[int] = mapped_column(
        ForeignKey("apple_ads_keywords.id", ondelete="CASCADE"), index=True
    )
    metric_date: Mapped[Date] = mapped_column(SADate, index=True)
    country_or_region: Mapped[str] = mapped_column(String(10), index=True)
    device_class: Mapped[str] = mapped_column(String(20), index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    taps: Mapped[int] = mapped_column(Integer, default=0)
    local_spend: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    currency: Mapped[str | None] = mapped_column(String(3))
    tap_installs: Mapped[int] = mapped_column(Integer, default=0)
    total_installs: Mapped[int] = mapped_column(Integer, default=0)
    ttr: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    cpt: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    suggested_bid: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    keyword: Mapped[AppleAdsKeyword] = relationship(back_populates="metrics")


class AppleAdsSuggestion(Base):
    """Apple's latest read-only keyword suggestion for one app and market."""

    __tablename__ = "apple_ads_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "app_id",
            "country_or_region",
            "normalized_text",
            name="uq_apple_ads_suggestion",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    country_or_region: Mapped[str] = mapped_column(String(10), index=True)
    text: Mapped[str] = mapped_column(String(255))
    normalized_text: Mapped[str] = mapped_column(String(255), index=True)
    popularity: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CompetitorApp(Base):
    """A read-only app column in the keyword competitor matrix."""

    __tablename__ = "competitor_apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    apple_app_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    artwork_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    ranks: Mapped[list[CompetitorRank]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan"
    )


class CompetitorRank(Base):
    """Latest public App Store rank for a competitor keyword target."""

    __tablename__ = "competitor_ranks"
    __table_args__ = (
        UniqueConstraint(
            "competitor_app_id",
            "keyword_id",
            "storefront_id",
            "device",
            name="uq_competitor_rank_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_app_id: Mapped[int] = mapped_column(
        ForeignKey("competitor_apps.id", ondelete="CASCADE"), index=True
    )
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), index=True)
    storefront_id: Mapped[int] = mapped_column(ForeignKey("storefronts.id"), index=True)
    device: Mapped[str] = mapped_column(String(10), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rank: Mapped[int | None] = mapped_column(Integer)
    found: Mapped[bool] = mapped_column(Boolean)
    result_limit: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)

    competitor: Mapped[CompetitorApp] = relationship(back_populates="ranks")
