"""Localized listing generation and validation tests."""

from pathlib import Path

import pytest

from local_aso_tracker.config import Settings
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import add_app, add_storefront, save_listing_metadata
from local_aso_tracker.repositories.listing_localizations import list_localization_drafts
from local_aso_tracker.services.agent import ListingLocalizationResult
from local_aso_tracker.services.listing_localization import (
    ListingSource,
    generate_localization_drafts,
    validate_listing_localization,
)


def test_listing_validation_checks_lengths_repetition_and_title_order() -> None:
    invalid = validate_listing_localization(
        {
            "name": "AstroLingo",
            "subtitle": "AstroLingo lessons",
            "keywords": "astrology,astrology",
            "description": "Learn astrology.",
            "promotionalText": "",
            "whatsNew": "Initial release.",
        },
        source_fields={},
        brand_term="AstroLingo",
        goal="aso_seo_aeo",
    )

    assert invalid["hasErrors"] is True
    assert any("repeated" in issue["message"].lower() for issue in invalid["issues"])  # type: ignore[index]
    assert any("brand" in issue["message"].lower() for issue in invalid["issues"])  # type: ignore[index]

    valid = validate_listing_localization(
        {
            "name": "Learn Astrology AstroLingo",
            "subtitle": "Birth chart lessons",
            "keywords": "horoscope,zodiac",
            "description": "Learn astrology with structured lessons.",
            "promotionalText": "Start learning today.",
            "whatsNew": "Improved lessons.",
        },
        source_fields={},
        brand_term="AstroLingo",
        goal="aso_seo_aeo",
    )
    assert valid["hasErrors"] is False


def test_generation_groups_countries_by_locale_and_retries_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "AstroLingo", 6771773264, "com.example.astrolingo")
        add_storefront(session, "us", "United States")
        add_storefront(session, "mx", "Mexico")
        add_storefront(session, "ec", "Ecuador")
        save_listing_metadata(
            session,
            app.apple_app_id,
            "us",
            name="Learn Astrology AstroLingo",
            subtitle="Birth chart lessons",
            keyword_field="astrology,zodiac",
            channel_goal="aso_seo_aeo",
            brand_term="AstroLingo",
        )

    source = ListingSource(
        country="us",
        locale="en-US",
        language="English",
        fields={
            "name": "Learn Astrology AstroLingo",
            "subtitle": "Birth chart lessons",
            "keywords": "astrology,zodiac",
            "description": "Learn astrology with structured lessons.",
            "promotionalText": "",
            "whatsNew": "Initial release.",
            "supportUrl": "https://example.com/support",
            "marketingUrl": "https://example.com",
        },
        mode="local_public",
    )
    monkeypatch.setattr(
        "local_aso_tracker.services.listing_localization._listing_source",
        lambda **_kwargs: source,
    )
    calls = 0

    def fake_agent(**_kwargs: object) -> tuple[str, ListingLocalizationResult]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                "codex",
                ListingLocalizationResult(
                    name="AstroLingo",
                    subtitle="AstroLingo lecciones",
                    keywords="astrología,astrología",
                    description="Aprende astrología.",
                    promotionalText="",
                    whatsNew="Primera versión.",
                ),
            )
        return (
            "codex",
            ListingLocalizationResult(
                name="Aprender astrología AstroLingo",
                subtitle="Lecciones de carta natal",
                keywords="horóscopo,zodiaco",
                description="Aprende astrología con lecciones estructuradas.",
                promotionalText="Empieza hoy.",
                whatsNew="Lecciones mejoradas.",
            ),
        )

    monkeypatch.setattr(
        "local_aso_tracker.services.listing_localization.generate_listing_localization",
        fake_agent,
    )
    result = generate_localization_drafts(
        app_id=6771773264,
        main_country="us",
        target_countries=["mx", "ec"],
        provider="codex",
        settings=Settings(),
    )

    assert result.iterations == 2
    assert len(result.drafts) == 1
    draft = result.drafts[0]
    assert draft["targetLocale"] == "es-MX"
    assert draft["targetCountries"] == ["mx", "ec"]
    assert draft["status"] == "needs_review"
    assert len(draft["iterations"]) == 2  # type: ignore[arg-type]

    with session_scope() as session:
        stored = list_localization_drafts(session, app_id=1)
    assert len(stored) == 1
    assert stored[0].target_locale == "es-MX"

    regenerated = generate_localization_drafts(
        app_id=6771773264,
        main_country="us",
        target_countries=["mx", "ec"],
        provider="codex",
        settings=Settings(),
    )
    assert regenerated.iterations == 1
    with session_scope() as session:
        stored = list_localization_drafts(session, app_id=1)
    assert len(stored) == 1
    assert [item.iteration for item in stored[0].iterations] == [1]


def test_generation_requires_a_target_country(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with pytest.raises(ValueError, match="at least one target"):
        generate_localization_drafts(
            app_id=6771773264,
            main_country="us",
            target_countries=[],
            provider="codex",
            settings=Settings(),
        )


def test_generation_rejects_targets_sharing_the_source_locale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        add_app(session, "AstroLingo", 6771773264, "com.example.astrolingo")
        add_storefront(session, "us", "United States")
        add_storefront(session, "gb", "United Kingdom")
        add_storefront(session, "ie", "Ireland")

    with pytest.raises(ValueError, match="same App Store locale"):
        generate_localization_drafts(
            app_id=6771773264,
            main_country="gb",
            target_countries=["ie"],
            provider="codex",
            settings=Settings(),
        )
