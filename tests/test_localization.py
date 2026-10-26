"""Curated multilingual keyword localization tests."""

from local_aso_tracker.services.localization import localization_payload, localize_keywords


def test_localization_routes_terms_to_matching_storefront_languages() -> None:
    groups, warnings = localize_keywords(
        ["birth chart", "astrology course"],
        ["us", "fr", "mx", "ca"],
    )

    by_language = {group.language_code: group for group in groups}
    assert warnings == []
    assert by_language["en"].countries == ["us", "ca"]
    assert by_language["en"].keywords == ["birth chart", "astrology course"]
    assert by_language["fr"].countries == ["fr", "ca"]
    assert by_language["fr"].keywords == ["thème astral", "cours d'astrologie"]
    assert by_language["es"].countries == ["us", "mx"]
    assert by_language["es"].keywords == ["carta natal", "curso de astrología"]


def test_unknown_phrases_are_skipped_in_foreign_markets_with_warnings() -> None:
    groups, warnings = localize_keywords(["moon ritual planner"], ["us", "fr"])

    assert [(group.language_code, group.keywords) for group in groups] == [
        ("en", ["moon ritual planner"])
    ]
    assert warnings == [
        {
            "keyword": "moon ritual planner",
            "language": "French",
            "reason": "No curated translation; skipped for this language.",
        },
        {
            "keyword": "moon ritual planner",
            "language": "Spanish",
            "reason": "No curated translation; skipped for this language.",
        },
    ]


def test_localization_payload_is_json_serializable_shape() -> None:
    payload = localization_payload(["zodiac signs"], ["es", "gb"])

    assert payload["sourceKeywords"] == ["zodiac signs"]
    assert payload["countries"] == ["es", "gb"]
    assert len(payload["groups"]) == 2  # type: ignore[arg-type]


def test_existing_catalog_variants_resolve_to_curated_translations() -> None:
    groups, warnings = localize_keywords(
        ["cours astrologie", "learn chart reading", "zodiac signs meaning"],
        ["fr", "mx"],
    )

    by_language = {group.language_code: group for group in groups}
    assert warnings == []
    assert by_language["fr"].keywords == [
        "cours d'astrologie",
        "apprendre à lire le thème astral",
        "signification des signes astrologiques",
    ]
    assert by_language["es"].keywords == [
        "curso de astrología",
        "aprender a leer carta astral",
        "significado de los signos zodiacales",
    ]
