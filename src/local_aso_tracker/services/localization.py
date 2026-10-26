"""Curated English, French, and Spanish keyword localization for App Store markets."""

from __future__ import annotations

from dataclasses import asdict, dataclass

LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}
COUNTRY_LANGUAGES = {
    "ar": ("es",),
    "au": ("en",),
    "bo": ("es",),
    "bz": ("es",),
    "ca": ("en", "fr"),
    "cl": ("es",),
    "co": ("es",),
    "cr": ("es",),
    "do": ("es",),
    "ec": ("es",),
    "es": ("es",),
    "fr": ("fr",),
    "gb": ("en",),
    "gt": ("es",),
    "hn": ("es",),
    "mx": ("es",),
    "ni": ("es",),
    "pa": ("es",),
    "pe": ("es",),
    "py": ("es",),
    "sv": ("es",),
    "us": ("en", "es"),
    "uy": ("es",),
    "ve": ("es",),
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "astrolingo": {"en": "astrolingo", "fr": "astrolingo", "es": "astrolingo"},
    "learn astrology": {
        "en": "learn astrology",
        "fr": "apprendre l'astrologie",
        "es": "aprender astrología",
    },
    "astrology": {"en": "astrology", "fr": "astrologie", "es": "astrología"},
    "astrology for beginners": {
        "en": "astrology for beginners",
        "fr": "astrologie pour débutants",
        "es": "astrología para principiantes",
    },
    "astrology course": {
        "en": "astrology course",
        "fr": "cours d'astrologie",
        "es": "curso de astrología",
    },
    "astrology lessons": {
        "en": "astrology lessons",
        "fr": "leçons d'astrologie",
        "es": "lecciones de astrología",
    },
    "astrology class": {
        "en": "astrology class",
        "fr": "cours d'astrologie",
        "es": "clase de astrología",
    },
    "astrology classes": {
        "en": "astrology classes",
        "fr": "cours d'astrologie",
        "es": "clases de astrología",
    },
    "astrology school": {
        "en": "astrology school",
        "fr": "école d'astrologie",
        "es": "escuela de astrología",
    },
    "astrology teacher": {
        "en": "astrology teacher",
        "fr": "professeur d'astrologie",
        "es": "profesor de astrología",
    },
    "astrologer": {
        "en": "astrologer",
        "fr": "astrologue",
        "es": "astrólogo",
    },
    "astrology tutorial": {
        "en": "astrology tutorial",
        "fr": "tutoriel d'astrologie",
        "es": "tutorial de astrología",
    },
    "astrology study": {
        "en": "astrology study",
        "fr": "étudier l'astrologie",
        "es": "estudiar astrología",
    },
    "study astrology": {
        "en": "study astrology",
        "fr": "étudier l'astrologie",
        "es": "estudiar astrología",
    },
    "astrology basics": {
        "en": "astrology basics",
        "fr": "bases de l'astrologie",
        "es": "bases de astrología",
    },
    "learn astrology basics": {
        "en": "learn astrology basics",
        "fr": "apprendre les bases de l'astrologie",
        "es": "aprender bases de astrología",
    },
    "astrology app": {
        "en": "astrology app",
        "fr": "application d'astrologie",
        "es": "app de astrología",
    },
    "astrology quiz": {
        "en": "astrology quiz",
        "fr": "quiz d'astrologie",
        "es": "test de astrología",
    },
    "astrology test": {
        "en": "astrology test",
        "fr": "test d'astrologie",
        "es": "test de astrología",
    },
    "astrology guide": {
        "en": "astrology guide",
        "fr": "guide d'astrologie",
        "es": "guía de astrología",
    },
    "learn birth chart": {
        "en": "learn birth chart",
        "fr": "apprendre le thème astral",
        "es": "aprender carta natal",
    },
    "birth chart": {
        "en": "birth chart",
        "fr": "thème astral",
        "es": "carta natal",
    },
    "natal chart": {
        "en": "natal chart",
        "fr": "thème natal",
        "es": "carta natal",
    },
    "birth chart lessons": {
        "en": "birth chart lessons",
        "fr": "leçons de thème astral",
        "es": "lecciones de carta natal",
    },
    "birth chart course": {
        "en": "birth chart course",
        "fr": "cours de thème astral",
        "es": "curso de carta natal",
    },
    "birth chart interpretation": {
        "en": "birth chart interpretation",
        "fr": "interprétation du thème astral",
        "es": "interpretación de carta natal",
    },
    "read birth chart": {
        "en": "read birth chart",
        "fr": "lire le thème astral",
        "es": "leer carta natal",
    },
    "learn chart reading": {
        "en": "learn chart reading",
        "fr": "apprendre à lire le thème astral",
        "es": "aprender a leer carta astral",
    },
    "learn natal chart": {
        "en": "learn natal chart",
        "fr": "apprendre le thème natal",
        "es": "aprender carta natal",
    },
    "birth chart reading": {
        "en": "birth chart reading",
        "fr": "lecture du thème astral",
        "es": "lectura de carta natal",
    },
    "birth chart app": {
        "en": "birth chart app",
        "fr": "application de thème astral",
        "es": "app de carta natal",
    },
    "natal chart app": {
        "en": "natal chart app",
        "fr": "application de thème natal",
        "es": "app de carta natal",
    },
    "birth chart guide": {
        "en": "birth chart guide",
        "fr": "guide du thème astral",
        "es": "guía de carta natal",
    },
    "birth chart explained": {
        "en": "birth chart explained",
        "fr": "thème astral expliqué",
        "es": "carta natal explicada",
    },
    "astrology houses": {
        "en": "astrology houses",
        "fr": "maisons astrologiques",
        "es": "casas astrológicas",
    },
    "astrology aspects": {
        "en": "astrology aspects",
        "fr": "aspects astrologiques",
        "es": "aspectos astrológicos",
    },
    "planets astrology": {
        "en": "planets astrology",
        "fr": "planètes en astrologie",
        "es": "planetas en astrología",
    },
    "zodiac signs": {
        "en": "zodiac signs",
        "fr": "signes astrologiques",
        "es": "signos zodiacales",
    },
    "zodiac signs meaning": {
        "en": "zodiac signs meaning",
        "fr": "signification des signes astrologiques",
        "es": "significado de los signos zodiacales",
    },
    "learn zodiac signs": {
        "en": "learn zodiac signs",
        "fr": "apprendre les signes astrologiques",
        "es": "aprender signos zodiacales",
    },
    "zodiac app": {
        "en": "zodiac app",
        "fr": "application de signes astrologiques",
        "es": "app de signos zodiacales",
    },
    "horoscope": {"en": "horoscope", "fr": "horoscope", "es": "horóscopo"},
    "horoscope app": {
        "en": "horoscope app",
        "fr": "application d'horoscope",
        "es": "app de horóscopo",
    },
    "daily horoscope": {
        "en": "daily horoscope",
        "fr": "horoscope du jour",
        "es": "horóscopo diario",
    },
    "horoscope quiz": {
        "en": "horoscope quiz",
        "fr": "quiz d'horoscope",
        "es": "test de horóscopo",
    },
    "astrology chart": {
        "en": "astrology chart",
        "fr": "thème astral",
        "es": "carta astral",
    },
    "chart reading": {
        "en": "chart reading",
        "fr": "lecture du thème astral",
        "es": "lectura de carta astral",
    },
    "natal chart interpretation": {
        "en": "natal chart interpretation",
        "fr": "interprétation du thème natal",
        "es": "interpretación de carta natal",
    },
    "natal chart reading": {
        "en": "natal chart reading",
        "fr": "lecture du thème natal",
        "es": "lectura de carta natal",
    },
}

ALIASES: dict[str, str] = {}
for canonical, variants in TRANSLATIONS.items():
    for phrase in variants.values():
        ALIASES[" ".join(phrase.casefold().split())] = canonical
ALIASES.update(
    {
        "aprender astrología": "learn astrology",
        "apprendre l'astrologie": "learn astrology",
        "apprendre astrologie": "learn astrology",
        "learning astrology": "learn astrology",
        "learn astro": "learn astrology",
        "astrología": "astrology",
        "astrologie": "astrology",
        "curso de astrología": "astrology course",
        "cours d'astrologie": "astrology course",
        "cours astrologie": "astrology course",
        "formation astrologie": "astrology course",
        "astrologie pour débutants": "astrology for beginners",
        "astrologie débutant": "astrology for beginners",
        "astrología para principiantes": "astrology for beginners",
        "bases astrologie": "astrology basics",
        "lecciones de astrología": "astrology lessons",
        "leçons d'astrologie": "astrology lessons",
        "test de astrología": "astrology quiz",
        "quiz astrologie": "astrology quiz",
        "app de astrología": "astrology app",
        "application astrologie": "astrology app",
        "carta natal": "birth chart",
        "thème astral": "birth chart",
        "theme astral": "birth chart",
        "thème natal": "natal chart",
        "carta astral": "astrology chart",
        "lire un thème astral": "read birth chart",
        "lire thème astral": "read birth chart",
        "comprendre thème astral": "birth chart guide",
        "interprétation thème astral": "birth chart interpretation",
        "maisons astrologiques": "astrology houses",
        "aspects astrologiques": "astrology aspects",
        "planètes astrologie": "planets astrology",
        "signes astrologiques": "zodiac signs",
        "interprétation de carta astral": "birth chart interpretation",
        "cómo leer la carta astral": "read birth chart",
        "casas astrológicas": "astrology houses",
        "aspectos astrológicos": "astrology aspects",
        "planetas en astrología": "planets astrology",
        "signos zodiacales": "zodiac signs",
        "aprender carta astral": "learn birth chart",
        "astrología desde cero": "astrology basics",
        "interpretar carta astral": "birth chart interpretation",
        "aprender a leer carta astral": "read birth chart",
        "interpretar carta natal": "natal chart interpretation",
        "carte du ciel": "astrology chart",
    }
)


@dataclass(frozen=True)
class LocalizedGroup:
    language_code: str
    language: str
    countries: list[str]
    keywords: list[str]


def localize_keywords(
    keywords: list[str], countries: list[str]
) -> tuple[list[LocalizedGroup], list[dict[str, str]]]:
    """Return localized groups and explicit warnings for uncurated phrases."""

    groups: list[LocalizedGroup] = []
    warnings: list[dict[str, str]] = []
    for language_code, language in LANGUAGE_NAMES.items():
        language_countries = [
            country
            for country in countries
            if language_code in COUNTRY_LANGUAGES.get(country, ("en",))
        ]
        if not language_countries:
            continue
        translated: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            canonical = ALIASES.get(" ".join(keyword.casefold().split()))
            if canonical is None:
                if language_code != "en":
                    warnings.append(
                        {
                            "keyword": keyword,
                            "language": language,
                            "reason": "No curated translation; skipped for this language.",
                        }
                    )
                    continue
                candidate = keyword
            else:
                candidate = TRANSLATIONS[canonical][language_code]
            normalized = " ".join(candidate.casefold().split())
            if normalized not in seen:
                seen.add(normalized)
                translated.append(candidate)
        if translated:
            groups.append(
                LocalizedGroup(
                    language_code=language_code,
                    language=language,
                    countries=language_countries,
                    keywords=translated,
                )
            )
    return groups, warnings


def localization_payload(keywords: list[str], countries: list[str]) -> dict[str, object]:
    groups, warnings = localize_keywords(keywords, countries)
    return {
        "groups": [asdict(group) for group in groups],
        "warnings": warnings,
        "sourceKeywords": keywords,
        "countries": countries,
    }
