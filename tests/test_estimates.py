"""Ratings-only keyword estimate tests."""

from local_aso_tracker.apple.schemas import AppleSoftwareResult
from local_aso_tracker.services.estimates import estimate_keyword


def result(
    track_id: int,
    rating_count: int | None,
    average_rating: float | None = None,
) -> AppleSoftwareResult:
    return AppleSoftwareResult.model_validate(
        {
            "trackId": track_id,
            "userRatingCount": rating_count,
            "averageUserRating": average_rating,
        }
    )


def test_unrated_results_do_not_create_false_demand() -> None:
    estimates = estimate_keyword([result(1, None), result(2, 0)])

    assert estimates.volume is None
    assert estimates.difficulty is None
    assert estimates.sample_size == 0


def test_estimates_are_bounded_and_more_rated_results_add_confidence() -> None:
    sparse = estimate_keyword([result(1, 50_000, 4.8)])
    broad = estimate_keyword([result(index, 50_000, 4.8) for index in range(1, 11)])

    assert sparse.volume is not None and broad.volume is not None
    assert broad.volume > sparse.volume
    assert broad.difficulty is not None and sparse.difficulty is not None
    assert broad.difficulty > sparse.difficulty
    assert 0 <= sparse.volume <= broad.volume <= 100
    assert 0 <= sparse.difficulty <= broad.difficulty <= 100
    assert broad.sample_size == 10


def test_top_result_ratings_carry_more_weight_than_lower_results() -> None:
    top_heavy = estimate_keyword(
        [result(1, 500_000, 4.9), *[result(index, 10, 4.0) for index in range(2, 11)]]
    )
    bottom_heavy = estimate_keyword(
        [result(1, 10, 4.0), *[result(index, 10, 4.0) for index in range(2, 11)]]
    )

    assert top_heavy.volume is not None
    assert bottom_heavy.volume is not None
    assert top_heavy.volume > bottom_heavy.volume
