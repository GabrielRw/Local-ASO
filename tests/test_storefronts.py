"""Storefront registry: markets, languages, App Store locales, and adding storefronts."""

from pathlib import Path

import pytest

from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import Storefront
from local_aso_tracker.services.localization_targets import (
    app_store_locale_for_country,
    language_for_country,
)
from local_aso_tracker.services.storefronts import (
    APP_STORE_LOCALE_LANGUAGE,
    MARKETS,
    require_market,
)
from local_aso_tracker.web.server import DashboardService


def test_registry_covers_the_major_app_store_markets() -> None:
    assert len(MARKETS) >= 55
    for code in ("us", "gb", "de", "fr", "jp", "kr", "br", "cn", "pt", "ua", "ro", "ae"):
        assert code in MARKETS, code
    # Every locale is a real App Store Connect localization with a known language.
    assert {item.locale for item in MARKETS.values()} <= set(APP_STORE_LOCALE_LANGUAGE)


def test_language_and_listing_locale_agree() -> None:
    # The Philippines used to audit in Filipino while localizing listings in English.
    assert language_for_country("ph") == "English"
    assert app_store_locale_for_country("ph") == "en-US"
    assert language_for_country("bz") == "English"
    assert (language_for_country("ua"), app_store_locale_for_country("ua")) == ("Ukrainian", "uk")
    assert (language_for_country("pt"), app_store_locale_for_country("pt")) == (
        "Portuguese",
        "pt-PT",
    )


def test_unknown_storefronts_are_rejected() -> None:
    with pytest.raises(ValueError, match="not a supported App Store storefront"):
        require_market("zz")


def test_dashboard_adds_a_storefront_with_its_registry_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    service = DashboardService()
    result = service.add_country({"code": "DE"})
    assert result == {"created": True, "country": {"code": "de", "name": "Germany", "active": True}}
    assert service.add_country({"code": "de"})["created"] is False
    with pytest.raises(ValueError):
        service.add_country({"code": "zz"})
    with session_scope() as session:
        stored = session.query(Storefront).filter_by(country_code="de").one()
        assert stored.display_name == "Germany"
    markets = service.bootstrap(None, "us")["markets"]
    assert {"code": "de", "name": "Germany", "language": "German"} in markets  # type: ignore[operator]
