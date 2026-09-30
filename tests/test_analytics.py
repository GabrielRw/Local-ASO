"""Rank movement and summary calculation tests."""

from datetime import UTC, datetime

import pytest

from local_aso_tracker.models import App, Keyword, RankCheck, Storefront, TrackingTarget
from local_aso_tracker.services.analytics import RankingRow, calculate_summary, movement


def check(rank: int | None, found: bool = True) -> RankCheck:
    return RankCheck(
        tracking_target_id=1,
        checked_at=datetime.now(UTC),
        rank=rank,
        found=found,
        result_limit=200,
        response_time_ms=1,
        status="success",
    )


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (check(10), check(20), "+10"),
        (check(20), check(10), "-10"),
        (check(10), check(10), "—"),
        (check(20), check(None, False), "NEW"),
        (check(None, False), check(20), "LOST"),
    ],
)
def test_rank_movement(current: RankCheck, previous: RankCheck, expected: str) -> None:
    assert movement(current, previous) == expected


def row(keyword: str, rank: int | None, previous: int | None = None) -> RankingRow:
    target = TrackingTarget(
        id=hash(keyword) % 10000,
        app=App(name="App", apple_app_id=1),
        keyword=Keyword(keyword=keyword, normalized_keyword=keyword),
        storefront=Storefront(country_code="us", display_name="United States"),
    )
    return RankingRow(
        target,
        check(rank, rank is not None),
        check(previous, previous is not None) if previous is not None else None,
    )


def test_summary_excludes_absent_from_average() -> None:
    summary = calculate_summary(
        [row("best", 5, 15), row("middle", 15, 10), row("absent", None, 30)]
    )
    assert summary.tracked_keywords == 3
    assert summary.top_10 == 1
    assert summary.top_20 == 2
    assert summary.absent == 1
    assert summary.average_rank == 10
    assert summary.best_keyword == "best (#5)"
    assert summary.newly_ranked == 0
    assert summary.lost == 1
