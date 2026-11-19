"""The App Store markets Local ASO researches, each with its listing locale and language.

One registry drives storefront names, the language audits and keyword translation use,
and the App Store Connect locale that localized listings are written to. Locales are
App Store Connect codes; several storefronts share one (all of Latin America -> es-MX).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    code: str
    name: str
    locale: str
    language: str


# App Store Connect localization codes and the language each one is written in.
APP_STORE_LOCALE_LANGUAGE: dict[str, str] = {
    "ar-SA": "Arabic",
    "ca": "Catalan",
    "cs": "Czech",
    "da": "Danish",
    "de-DE": "German",
    "el": "Greek",
    "en-AU": "English",
    "en-CA": "English",
    "en-GB": "English",
    "en-US": "English",
    "es-ES": "Spanish",
    "es-MX": "Spanish",
    "fi": "Finnish",
    "fr-CA": "French",
    "fr-FR": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "nl-NL": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt-BR": "Portuguese",
    "pt-PT": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh-Hans": "Chinese",
    "zh-Hant": "Chinese",
}

_MARKETS: tuple[tuple[str, str, str], ...] = (
    # code, English name, App Store Connect locale
    ("ae", "United Arab Emirates", "ar-SA"),
    ("ar", "Argentina", "es-MX"),
    ("at", "Austria", "de-DE"),
    ("au", "Australia", "en-AU"),
    ("be", "Belgium", "nl-NL"),
    ("bo", "Bolivia", "es-MX"),
    ("br", "Brazil", "pt-BR"),
    ("bz", "Belize", "en-US"),
    ("ca", "Canada", "en-CA"),
    ("ch", "Switzerland", "de-DE"),
    ("cl", "Chile", "es-MX"),
    ("cn", "China mainland", "zh-Hans"),
    ("co", "Colombia", "es-MX"),
    ("cr", "Costa Rica", "es-MX"),
    ("cz", "Czechia", "cs"),
    ("de", "Germany", "de-DE"),
    ("dk", "Denmark", "da"),
    ("do", "Dominican Republic", "es-MX"),
    ("ec", "Ecuador", "es-MX"),
    ("eg", "Egypt", "ar-SA"),
    ("es", "Spain", "es-ES"),
    ("fi", "Finland", "fi"),
    ("fr", "France", "fr-FR"),
    ("gb", "United Kingdom", "en-GB"),
    ("gr", "Greece", "el"),
    ("gt", "Guatemala", "es-MX"),
    ("hk", "Hong Kong", "zh-Hant"),
    ("hn", "Honduras", "es-MX"),
    ("hr", "Croatia", "hr"),
    ("hu", "Hungary", "hu"),
    ("id", "Indonesia", "id"),
    ("ie", "Ireland", "en-GB"),
    ("il", "Israel", "he"),
    ("in", "India", "en-GB"),
    ("it", "Italy", "it"),
    ("jp", "Japan", "ja"),
    ("kr", "South Korea", "ko"),
    ("kz", "Kazakhstan", "ru"),
    ("lu", "Luxembourg", "fr-FR"),
    ("mx", "Mexico", "es-MX"),
    ("my", "Malaysia", "ms"),
    ("ng", "Nigeria", "en-GB"),
    ("ni", "Nicaragua", "es-MX"),
    ("nl", "Netherlands", "nl-NL"),
    ("no", "Norway", "no"),
    ("nz", "New Zealand", "en-AU"),
    ("pa", "Panama", "es-MX"),
    ("pe", "Peru", "es-MX"),
    ("ph", "Philippines", "en-US"),
    ("pk", "Pakistan", "en-GB"),
    ("pl", "Poland", "pl"),
    ("pt", "Portugal", "pt-PT"),
    ("py", "Paraguay", "es-MX"),
    ("ro", "Romania", "ro"),
    ("ru", "Russia", "ru"),
    ("sa", "Saudi Arabia", "ar-SA"),
    ("se", "Sweden", "sv"),
    ("sg", "Singapore", "en-GB"),
    ("sk", "Slovakia", "sk"),
    ("sv", "El Salvador", "es-MX"),
    ("th", "Thailand", "th"),
    ("tr", "Türkiye", "tr"),
    ("tw", "Taiwan", "zh-Hant"),
    ("ua", "Ukraine", "uk"),
    ("us", "United States", "en-US"),
    ("uy", "Uruguay", "es-MX"),
    ("ve", "Venezuela", "es-MX"),
    ("vn", "Vietnam", "vi"),
    ("za", "South Africa", "en-GB"),
)

MARKETS: dict[str, Market] = {
    code: Market(code, name, locale, APP_STORE_LOCALE_LANGUAGE[locale])
    for code, name, locale in _MARKETS
}


def market(code: str) -> Market | None:
    return MARKETS.get(code.strip().lower())


def require_market(code: str) -> Market:
    """The registry entry for a storefront code, or a clear error for unknown codes."""

    found = market(code)
    if found is None:
        raise ValueError(
            f"{code.strip().upper() or 'That code'} is not a supported App Store storefront"
        )
    return found
