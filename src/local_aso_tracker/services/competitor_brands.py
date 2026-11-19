"""Recognize searches for other apps' brand names.

App Review Guideline 2.3.7 forbids other apps' names in a listing's metadata, but those
searches are legitimate Apple Ads keywords. A keyword is treated as a competitor brand
when it equals the leading words of a known app name (ignoring case, spacing,
punctuation, and accents) and is not generic: if every word of the keyword appears in
the names of several different apps ("horoscopes", "zodiac signs"), it describes the
category rather than one product.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

GENERIC_MIN_APPS = 3
MAX_PREFIX_WORDS = 3
MIN_BRAND_LENGTH = 3
# Name separators: colon, bar, middle dot, parenthesis, comma, or a spaced hyphen/en/em dash.
_SEGMENT_BREAK = re.compile(r"\s*(?::|\||\u00b7|\(|,|\s[-\u2013\u2014]\s)\s*")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def words(text: str) -> list[str]:
    """Lower-case, accent-free words of ``text``."""

    return re.findall(r"[^\W_]+", _fold(text))


def _stem(word: str) -> str:
    """Fold simple plurals so "horoscopes" and "horoscope" count as one category word."""

    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def squash(text: str) -> str:
    """``text`` with case, accents, spaces, and punctuation removed."""

    return "".join(words(text))


class BrandIndex:
    """Brand lookup built from app names that Apple returned for local searches."""

    def __init__(self, apps: Iterable[tuple[int, str]], *, exclude_ids: Iterable[int] = ()) -> None:
        excluded = set(exclude_ids)
        self._owners: dict[str, str] = {}
        apps_by_word: dict[str, set[int]] = defaultdict(set)
        for app_id, name in apps:
            if app_id in excluded or not name.strip():
                continue
            for word in {_stem(word) for word in words(name)}:
                apps_by_word[word].add(app_id)
            segment = _SEGMENT_BREAK.split(name.strip(), maxsplit=1)[0]
            segment_words = words(segment)
            prefixes = {"".join(segment_words)}
            prefixes.update(
                "".join(segment_words[:count])
                for count in range(1, min(MAX_PREFIX_WORDS, len(segment_words)) + 1)
            )
            for prefix in prefixes:
                if len(prefix) >= MIN_BRAND_LENGTH:
                    # Keep the shortest app name as the readable owner.
                    current = self._owners.get(prefix)
                    if current is None or len(name) < len(current):
                        self._owners[prefix] = name.strip()
        self._app_counts = {word: len(ids) for word, ids in apps_by_word.items()}

    def is_generic(self, keyword: str) -> bool:
        keyword_words = words(keyword)
        return bool(keyword_words) and all(
            self._app_counts.get(_stem(word), 0) >= GENERIC_MIN_APPS for word in keyword_words
        )

    def owner(self, keyword: str) -> str | None:
        """The app whose brand ``keyword`` is, or ``None`` for a non-brand search."""

        key = squash(keyword)
        if len(key) < MIN_BRAND_LENGTH or self.is_generic(keyword):
            return None
        return self._owners.get(key)
