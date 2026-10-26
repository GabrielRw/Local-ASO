"""Database uniqueness and latest-rank query tests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from local_aso_tracker.models import RankCheck
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    latest_pairs,
    list_targets,
)


def make_target(session: Session) -> int:
    add_app(session, "AstroLingo", 6771773264)
    add_keyword(session, "learn astrology")
    add_storefront(session, "us", "United States")
    target, _ = add_target(session, 6771773264, "learn astrology", "us")
    return target.id


def test_duplicate_keyword_and_target_prevention(session: Session) -> None:
    target_id = make_target(session)
    keyword, keyword_created = add_keyword(session, " Learn   Astrology ")
    target, target_created = add_target(session, 6771773264, "LEARN ASTROLOGY", "US")
    assert keyword_created is False
    assert target_created is False
    assert target.id == target_id
    assert keyword.normalized_keyword == "learn astrology"

    ipad, ipad_created = add_target(session, 6771773264, "learn astrology", "us", "ipad")
    assert ipad_created is True
    assert ipad.id != target_id
    assert ipad.device == "ipad"
    assert len(list_targets(session, device="iphone")) == 1
    assert len(list_targets(session, device="ipad")) == 1


def test_latest_rank_query_returns_latest_and_previous(session: Session) -> None:
    target_id = make_target(session)
    now = datetime.now(UTC)
    session.add_all(
        [
            RankCheck(
                tracking_target_id=target_id,
                checked_at=now - timedelta(days=1),
                rank=20,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            ),
            RankCheck(
                tracking_target_id=target_id,
                checked_at=now,
                rank=10,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            ),
        ]
    )
    session.flush()
    pair = latest_pairs(session, list_targets(session))[target_id]
    assert pair[0].rank == 10
    assert pair[1] is not None and pair[1].rank == 20


def test_adding_an_existing_app_reactivates_it(session: Session) -> None:
    app, created = add_app(session, "Original name", 123)
    assert created is True
    app.active = False
    session.flush()

    restored, created_again = add_app(session, "Updated name", 123)

    assert created_again is False
    assert restored.id == app.id
    assert restored.active is True
