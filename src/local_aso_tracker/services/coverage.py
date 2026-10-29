"""Local listing-keyword coverage analysis based on stored rank checks."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

DISTRIBUTION_GOALS = {
    "aso_seo_aeo": "ASO / SEO / AEO",
    "ugc_ads": "UGC / Ads",
}

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
class UntrackedKeyword:
    keyword: str
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
    untracked_terms: int
    untracked_matches: list[UntrackedKeyword]


@dataclass(frozen=True)
class WordUsage:
    word: str
    title_count: int
    subtitle_count: int
    keyword_count: int
    total: int
    fields: list[str]


@dataclass(frozen=True)
class StrategyPrinciple:
    key: str
    label: str
    passed: bool | None
    detail: str


@dataclass(frozen=True)
class DistributionStrategyAnalysis:
    goal: str
    goal_label: str
    brand_term: str
    word_analysis: list[WordUsage]
    duplicate_words: list[WordUsage]
    no_repetition: StrategyPrinciple
    title_order: StrategyPrinciple


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
    tracked_items = list(tracked)
    for item in tracked_items:
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
    tracked_tokens = {token for item in tracked_items for token in _analysis_tokens(item.keyword)}
    untracked_keywords: dict[str, str] = {}
    untracked_sources: dict[str, list[str]] = {}
    for field_name, values in (
        ("Name", title_terms),
        ("Subtitle", subtitle_terms),
        ("Keywords", keyword_entries),
    ):
        for value in values:
            normalized = _searchable(value)
            tokens = _analysis_tokens(value)
            if not normalized or (tokens and all(token in tracked_tokens for token in tokens)):
                continue
            untracked_keywords.setdefault(normalized, value.strip())
            candidate_sources = untracked_sources.setdefault(normalized, [])
            if field_name not in candidate_sources:
                candidate_sources.append(field_name)
    untracked_matches = [
        UntrackedKeyword(
            keyword=untracked_keywords[normalized],
            sources=sources,
        )
        for normalized, sources in sorted(
            untracked_sources.items(),
            key=lambda item: untracked_keywords[item[0]].casefold(),
        )
    ]
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
        untracked_terms=len(untracked_matches),
        untracked_matches=untracked_matches,
    )


def analyze_distribution_strategy(
    name: str,
    subtitle: str,
    keyword_field: str,
    *,
    goal: str,
    brand_term: str,
) -> DistributionStrategyAnalysis:
    """Verify duplicate keyword use and goal-specific title ordering."""

    if goal not in DISTRIBUTION_GOALS:
        raise ValueError("distribution goal must be aso_seo_aeo or ugc_ads")
    field_tokens = {
        "Name": _analysis_tokens(name),
        "Subtitle": _analysis_tokens(subtitle),
        "Keywords": _analysis_tokens(keyword_field),
    }
    occurrences: dict[str, dict[str, int]] = {}
    for field, tokens in field_tokens.items():
        for token in tokens:
            counts = occurrences.setdefault(token, {})
            counts[field] = counts.get(field, 0) + 1
    words = [
        WordUsage(
            word=word,
            title_count=counts.get("Name", 0),
            subtitle_count=counts.get("Subtitle", 0),
            keyword_count=counts.get("Keywords", 0),
            total=sum(counts.values()),
            fields=[field for field in ("Name", "Subtitle", "Keywords") if counts.get(field)],
        )
        for word, counts in occurrences.items()
    ]
    words.sort(key=lambda item: (-item.total, item.word))
    duplicates = [item for item in words if item.total > 1]
    duplicate_detail = (
        "No meaningful word appears more than once across the three indexed fields."
        if not duplicates
        else "Repeated words: "
        + "; ".join(
            f"{item.word} ({item.title_count} title, {item.subtitle_count} subtitle, "
            f"{item.keyword_count} keyword)"
            for item in duplicates[:10]
        )
        + ("…" if len(duplicates) > 10 else ".")
    )
    title_order_passed, title_order_detail = _title_order_check(
        name,
        goal=goal,
        brand_term=brand_term,
    )
    return DistributionStrategyAnalysis(
        goal=goal,
        goal_label=DISTRIBUTION_GOALS[goal],
        brand_term=" ".join(brand_term.split()),
        word_analysis=words,
        duplicate_words=duplicates,
        no_repetition=StrategyPrinciple(
            key="no_repetition",
            label="No repeated keywords across indexed fields",
            passed=not duplicates,
            detail=duplicate_detail,
        ),
        title_order=StrategyPrinciple(
            key="title_order",
            label=("Generic phrase before brand" if goal == "aso_seo_aeo" else "Brand term first"),
            passed=title_order_passed,
            detail=title_order_detail,
        ),
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


def _analysis_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return [
        token
        for token in re.findall(r"[a-z0-9]+", ascii_value)
        if len(token) > 1 and token not in STOP_WORDS
    ]


def _title_order_check(
    title: str,
    *,
    goal: str,
    brand_term: str,
) -> tuple[bool | None, str]:
    brand_tokens = _analysis_tokens(brand_term)
    if not brand_tokens:
        return None, "Enter a brand term to verify title ordering."
    title_tokens = _analysis_tokens(title)
    positions = [
        index
        for index in range(len(title_tokens) - len(brand_tokens) + 1)
        if title_tokens[index : index + len(brand_tokens)] == brand_tokens
    ]
    if not positions:
        return False, "The brand term was not found in the title."
    position = positions[0]
    if goal == "aso_seo_aeo":
        generic_before = position > 0
        generic_after = position + len(brand_tokens) < len(title_tokens)
        if generic_before and not generic_after:
            return (
                True,
                "A generic phrase appears before the brand, and the brand closes the title.",
            )
        if not generic_before:
            return False, "Move the brand after the generic keyword phrase for ASO/SEO/AEO."
        return False, "Move meaningful generic terms before the brand; keep the brand at the end."
    if position == 0:
        return True, "The brand is the first meaningful term in the title."
    return False, "For UGC/Ads, place the brand first so it is the primary search association."
