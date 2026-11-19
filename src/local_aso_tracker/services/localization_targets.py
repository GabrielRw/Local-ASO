"""Country -> language and App Store locale lookups (derived from the storefront registry)."""

from __future__ import annotations

from local_aso_tracker.services.storefronts import APP_STORE_LOCALE_LANGUAGE, MARKETS

COUNTRY_PRIMARY_LANGUAGE: dict[str, str] = {code: item.language for code, item in MARKETS.items()}
COUNTRY_TO_APP_STORE_LOCALE: dict[str, str] = {code: item.locale for code, item in MARKETS.items()}

__all__ = [
    "APP_STORE_LOCALE_LANGUAGE",
    "COUNTRY_PRIMARY_LANGUAGE",
    "COUNTRY_TO_APP_STORE_LOCALE",
    "app_store_locale_for_country",
    "language_for_country",
]


def app_store_locale_for_country(country_code: str) -> str:
    return COUNTRY_TO_APP_STORE_LOCALE.get(country_code.lower(), "en-US")


def language_for_country(country_code: str) -> str:
    return COUNTRY_PRIMARY_LANGUAGE.get(country_code.lower(), "English")
