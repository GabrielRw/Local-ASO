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


def test_other_markets_are_translated_by_the_local_ai() -> None:
    calls: list[tuple[list[str], list[str]]] = []

    def translator(keywords, languages):  # type: ignore[no-untyped-def]
        calls.append((list(keywords), list(languages)))
        return {
            "German": {"couples app": "paar app"},
            "Japanese": {"couples app": "カップル アプリ"},
            "Spanish": {"couples app": "app para parejas"},
        }

    groups, warnings = localize_keywords(["couples app"], ["us", "de", "jp"], translator=translator)
    by_language = {group.language: group for group in groups}
    assert warnings == []
    assert by_language["German"].countries == ["de"]
    assert by_language["German"].keywords == ["paar app"]
    assert by_language["German"].language_code == "de"
    assert by_language["Japanese"].keywords == ["カップル アプリ"]
    # The US storefront also searches in Spanish; English passes through untranslated.
    assert by_language["Spanish"].keywords == ["app para parejas"]
    assert by_language["English"].keywords == ["couples app"]
    # One batched call covers every language that needs a translation.
    assert len(calls) == 1
    assert set(calls[0][1]) == {"Spanish", "German", "Japanese"}


def test_non_english_markets_never_fall_back_to_english() -> None:
    groups, warnings = localize_keywords(["couples app"], ["de"])
    assert groups == []
    assert warnings[0]["language"] == "German"
    assert "No local AI provider" in warnings[0]["reason"]


def test_translator_failures_become_warnings() -> None:
    def broken(_keywords, _languages):  # type: ignore[no-untyped-def]
        raise RuntimeError("claude CLI is signed out")

    groups, warnings = localize_keywords(["couples app"], ["us", "de"], translator=broken)
    assert [group.language for group in groups] == ["English"]
    german = [item for item in warnings if item["language"] == "German"]
    assert german and german[0]["reason"].startswith("Translation failed: claude CLI is signed out")


def test_translation_output_is_filtered_to_what_was_asked(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from local_aso_tracker.services import agent

    monkeypatch.setattr(
        agent,
        "_run_structured_agent",
        lambda *_args, **_kwargs: (
            "claude",
            {
                "translations": [
                    {"language": "german", "keyword": "Couples App", "phrase": " paar  app "},
                    {"language": "Klingon", "keyword": "couples app", "phrase": "x"},
                    {"language": "German", "keyword": "not requested", "phrase": "y"},
                ]
            },
        ),
    )
    provider, result = agent.generate_keyword_translations(
        keywords=["couples app"], languages=["German"]
    )
    assert provider == "claude"
    assert result == {"German": {"couples app": "paar app"}}
