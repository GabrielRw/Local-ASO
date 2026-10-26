"""Local listing-keyword coverage analysis based on stored rank checks."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

STOP_WORDS = {
    "a",
    "an",
    "and",
    "app",
    "de",
    "des",
    "du",
    "el",
    "en",
    "et",
    "for",
    "la",
    "le",
    "les",
    "of",
    "para",
    "por",
    "the",
    "to",
    "un",
    "une",
    "your",
}


@dataclass(frozen=True)
class TrackedKeyword:
    keyword: str
    rank: int | None
    found: bool
    result_limit: int


@dataclass(frozen=True)
class MatchedKeyword:
    keyword: str
    rank: int | None
    found: bool
    result_limit: int
    sources: list[str]


@dataclass(frozen=True)
class CoverageAnalysis:
    target_terms: int
    keyword_field_terms: int
    title_terms: list[str]
    subtitle_terms: list[str]
    keyword_field_entries: list[str]
    tracked_matches: int
    ranked_keywords: int
    unranked_keywords: int
    matched: list[MatchedKeyword]


def analyze_listing_coverage(
    name: str,
    subtitle: str,
    keyword_field: str,
    tracked: Iterable[TrackedKeyword],
) -> CoverageAnalysis:
    """Compare listing terms with exact tracked phrases found in the metadata."""

    title_terms = _unique_terms(_word_terms(name))
    subtitle_terms = _unique_terms(_word_terms(subtitle))
    keyword_entries = _unique_terms(
        [" ".join(entry.split()) for entry in re.split(r"[,\n]+", keyword_field) if entry.strip()]
    )
    target_terms = len(set(title_terms) | set(subtitle_terms) | set(keyword_entries))
    metadata_parts = {
        "Name": _searchable(name),
        "Subtitle": _searchable(subtitle),
        "Keywords": _searchable(keyword_field),
    }
    matched: list[MatchedKeyword] = []
    for item in tracked:
        normalized = _searchable(item.keyword)
        if not normalized:
            continue
        sources = [
            source for source, text in metadata_parts.items() if f" {normalized} " in f" {text} "
        ]
        if sources:
            matched.append(
                MatchedKeyword(
                    keyword=item.keyword,
                    rank=item.rank,
                    found=item.found,
                    result_limit=item.result_limit,
                    sources=sources,
                )
            )
    ranked = sum(item.found and item.rank is not None for item in matched)
    return CoverageAnalysis(
        target_terms=target_terms,
        keyword_field_terms=len(keyword_entries),
        title_terms=title_terms,
        subtitle_terms=subtitle_terms,
        keyword_field_entries=keyword_entries,
        tracked_matches=len(matched),
        ranked_keywords=ranked,
        unranked_keywords=len(matched) - ranked,
        matched=matched,
    )


def _word_terms(value: str) -> list[str]:
    words = re.findall(r"[^\W_]+(?:['\u2019][^\W_]+)?", value.casefold(), flags=re.UNICODE)
    return [word for word in words if len(word) > 1 and word not in STOP_WORDS]


def _unique_terms(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(value.split()).strip()
        normalized = _searchable(cleaned)
        if cleaned and normalized not in seen:
            seen.add(normalized)
            result.append(cleaned)
    return result


def _searchable(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
