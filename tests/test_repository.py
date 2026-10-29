"""Database uniqueness and latest-rank query tests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from local_aso_tracker.models import RankCheck
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    filter_targets_due_for_check,
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


def test_freshness_filter_skips_recent_successes_but_keeps_failures_and_stale_checks(
    session: Session,
) -> None:
    recent_target_id = make_target(session)
    add_keyword(session, "birth chart")
    failed_target, _ = add_target(session, 6771773264, "birth chart", "us")
    add_keyword(session, "astrology lessons")
    stale_target, _ = add_target(session, 6771773264, "astrology lessons", "us")
    now = datetime.now(UTC)
    session.add_all(
        [
            RankCheck(
                tracking_target_id=recent_target_id,
                checked_at=now - timedelta(hours=2),
                rank=8,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            ),
            RankCheck(
                tracking_target_id=failed_target.id,
                checked_at=now - timedelta(hours=1),
                rank=None,
                found=False,
                result_limit=200,
                response_time_ms=10,
                status="error",
            ),
            RankCheck(
                tracking_target_id=stale_target.id,
                checked_at=now - timedelta(hours=25),
                rank=12,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            ),
        ]
    )
    session.flush()

    due, skipped = filter_targets_due_for_check(
        session,
        list_targets(session),
        cutoff=now - timedelta(hours=24),
    )

    assert {target.id for target in due} == {failed_target.id, stale_target.id}
    assert skipped == 1


def test_adding_an_existing_app_reactivates_it(session: Session) -> None:
    app, created = add_app(session, "Original name", 123)
    assert created is True
    app.active = False
    session.flush()

    restored, created_again = add_app(session, "Updated name", 123)

    assert created_again is False
    assert restored.id == app.id
    assert restored.active is True
