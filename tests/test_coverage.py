"""Listing metadata keyword-coverage analysis tests."""

from local_aso_tracker.services.coverage import TrackedKeyword, analyze_listing_coverage


def test_listing_coverage_counts_terms_and_tracked_rankings() -> None:
    analysis = analyze_listing_coverage(
        "Learn Astrology: AstroLingo",
        "Birth Chart Lessons",
        "birth chart, natal chart, astrology",
        [
            TrackedKeyword("learn astrology", 2, True, 200),
            TrackedKeyword("birth chart", None, False, 200),
            TrackedKeyword("astrology", 10, True, 200),
            TrackedKeyword("unrelated keyword", 5, True, 200),
        ],
    )

    assert analysis.target_terms == 8
    assert analysis.keyword_field_terms == 3
    assert analysis.tracked_matches == 3
    assert analysis.ranked_keywords == 2
    assert analysis.unranked_keywords == 1
    assert [item.keyword for item in analysis.matched] == [
        "learn astrology",
        "birth chart",
        "astrology",
    ]
    assert analysis.matched[1].sources == ["Subtitle", "Keywords"]


def test_listing_coverage_normalizes_accents_for_matching() -> None:
    analysis = analyze_listing_coverage(
        "Astrologie",
        "Thème astral",
        "thème natal",
        [TrackedKeyword("theme astral", 8, True, 200)],
    )

    assert analysis.tracked_matches == 1
    assert analysis.matched[0].sources == ["Subtitle"]
