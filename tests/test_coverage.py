"""Listing metadata keyword-coverage and strategy analysis tests."""

import pytest

from local_aso_tracker.services.coverage import (
    TrackedKeyword,
    analyze_distribution_strategy,
    analyze_listing_coverage,
)


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
    assert analysis.untracked_terms == 3
    assert [item.keyword for item in analysis.untracked_matches] == [
        "astrolingo",
        "lessons",
        "natal chart",
    ]
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


def test_strategy_analysis_detects_repeated_words_and_generic_first_title() -> None:
    analysis = analyze_distribution_strategy(
        "Astrology: AstroLingo",
        "Astrology guide",
        "astrology, birth chart",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )

    assert analysis.goal_label == "ASO / SEO / AEO"
    assert analysis.title_order.passed is True
    assert analysis.no_repetition.passed is False
    assert analysis.duplicate_words[0].word == "astrology"
    assert analysis.duplicate_words[0].total == 3
    assert analysis.word_analysis[0].title_count == 1


@pytest.mark.parametrize(
    ("goal", "title", "expected"),
    [
        ("aso_seo_aeo", "Learn Astrology: AstroLingo", True),
        ("aso_seo_aeo", "AstroLingo: Learn Astrology", False),
        ("ugc_ads", "AstroLingo: Learn Astrology", True),
        ("ugc_ads", "Learn Astrology: AstroLingo", False),
    ],
)
def test_title_order_depends_on_distribution_goal(
    goal: str,
    title: str,
    expected: bool,
) -> None:
    analysis = analyze_distribution_strategy(
        title,
        "Birth chart",
        "natal chart",
        goal=goal,
        brand_term="AstroLingo",
    )

    assert analysis.title_order.passed is expected
