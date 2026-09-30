"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class App(Base):
    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    apple_app_id: Mapped[int] = mapped_column(unique=True, index=True)
    bundle_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    targets: Mapped[list[TrackingTarget]] = relationship(back_populates="app")


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
