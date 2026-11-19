"""Competitor-brand search detection."""

from local_aso_tracker.services.competitor_brands import BrandIndex, squash

CATALOG = [
    (1, "Co\u2013Star Personalized Astrology"),
    (2, "CHANI: Your Astrology Guide"),
    (3, "Nebula: Spiritual Guidance"),
    (4, "The Pattern"),
    (5, "Horoscopes"),
    (6, "Horoscopes by Astrology.com"),
    (7, "Astrology Daily Horoscope"),
    (8, "Zodiac Signs!"),
    (9, "Zodiac Star Signs & Astrology"),
    (10, "Zodiac Psychics: Tarot Reading"),
    (11, "AstroLingo - Learn Astrology"),
    (12, "Star Signs Daily"),
]


def test_squash_ignores_case_spacing_punctuation_and_accents() -> None:
    assert squash("Co\u2013Star") == squash("costar") == "costar"
    assert squash("Pensée Positive") == "penseepositive"


def test_brand_names_match_leading_words_of_an_app_name() -> None:
    index = BrandIndex(CATALOG)
    assert index.owner("costar") == "Co\u2013Star Personalized Astrology"
    assert index.owner("co star") == "Co\u2013Star Personalized Astrology"
    assert index.owner("Chani") == "CHANI: Your Astrology Guide"
    assert index.owner("nebula") == "Nebula: Spiritual Guidance"
    assert index.owner("the pattern") == "The Pattern"


def test_category_words_shared_by_many_apps_are_not_brands() -> None:
    index = BrandIndex(CATALOG)
    for generic in ("horoscopes", "zodiac signs", "astrology", "zodiac"):
        assert index.owner(generic) is None, generic


def test_the_audited_app_and_unknown_terms_are_not_competitor_brands() -> None:
    index = BrandIndex(CATALOG, exclude_ids=[11])
    assert index.owner("astrolingo") is None
    assert index.owner("natal chart") is None
    assert index.owner("ab") is None
