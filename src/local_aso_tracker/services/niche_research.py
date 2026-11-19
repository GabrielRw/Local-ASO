"""Refresh Apple-public-data market estimates for niche research boards."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from local_aso_tracker.apple.client import AppleClientError, AppleSearchClient, SearchOutcome
from local_aso_tracker.config import Settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import NicheBoard, NicheKeywordTerm
from local_aso_tracker.repositories.niches import get_niche_board, upsert_niche_metric
from local_aso_tracker.services.estimates import estimate_keyword
from local_aso_tracker.services.localization import Translator, curated_phrase, market_languages


@dataclass(frozen=True)
class NicheCheckResult:
    searches: int
    failures: int


def localize_board_terms(
    board_id: int,
    *,
    translator: Translator | None,
    countries: set[str] | None = None,
) -> list[dict[str, str]]:
    """Store, per market, the phrase to search for each keyword in that market's language.

    English-language markets search the keyword itself. Curated phrases win, the rest come
    from one batched AI translation. Phrases that can't be localized are left out (and
    retried next time); their markets keep searching the source keyword and are flagged in
    the board. Returns warnings for those phrases.
    """

    with session_scope() as session:
        board = get_niche_board(session, board_id)
        if board is None:
            raise ValueError(f"unknown niche board: {board_id}")
        existing = {
            (term.niche_keyword_id, term.country_code)
            for keyword in board.keywords
            for term in keyword.terms
        }
        ids = {keyword.keyword: keyword.id for keyword in board.keywords}
        missing: list[tuple[str, str, str]] = []  # (country, language, keyword)
        for market in board.markets:
            country = market.country_code
            language = market_languages(country)[0]
            if (countries is not None and country not in countries) or language == "English":
                continue
            missing.extend(
                (country, language, keyword.keyword)
                for keyword in board.keywords
                if (keyword.id, country) not in existing
            )
    if not missing:
        return []

    resolved: dict[tuple[str, str], str] = {}
    pending: dict[str, set[str]] = {}
    for _country, language, keyword in missing:
        phrase = curated_phrase(keyword, language)
        if phrase:
            resolved[(language, keyword)] = phrase
        else:
            pending.setdefault(language, set()).add(keyword)
    failure: str | None = None
    if pending and translator is not None:
        try:
            translated = translator(
                sorted({keyword for items in pending.values() for keyword in items}), list(pending)
            )
        except Exception as exc:
            translated, failure = {}, str(exc)[:200]
        for language, items in translated.items():
            for keyword, phrase in items.items():
                if language in pending and keyword in pending[language] and phrase.strip():
                    resolved[(language, keyword)] = " ".join(phrase.split())

    warnings: list[dict[str, str]] = []
    with session_scope() as session:
        for country, language, keyword in missing:
            phrase = resolved.get((language, keyword))
            if phrase is None:
                warnings.append(
                    {
                        "keyword": keyword,
                        "language": language,
                        "reason": (
                            f"Translation failed: {failure}"
                            if failure
                            else "No local AI provider translated it; searched as written."
                        ),
                    }
                )
                continue
            session.add(
                NicheKeywordTerm(
                    niche_keyword_id=ids[keyword],
                    country_code=country,
                    term=phrase[:255],
                    language=language,
                )
            )
    return warnings


@dataclass(frozen=True)
class NicheSearchTarget:
    keyword_id: int
    keyword: str
    country: str


async def refresh_niche_metrics_async(
    board_id: int,
    settings: Settings,
    *,
    client: AppleSearchClient | None = None,
    keyword_ids: set[int] | None = None,
    countries: set[str] | None = None,
) -> NicheCheckResult:
    """Refresh all keyword/country pairs in one niche board."""

    with session_scope() as session:
        board = get_niche_board(session, board_id)
        if board is None:
            raise ValueError(f"unknown niche board: {board_id}")
        terms = {
            (term.niche_keyword_id, term.country_code): term.term
            for keyword in board.keywords
            for term in keyword.terms
        }
        targets = [
            NicheSearchTarget(
                keyword_id=keyword.id,
                keyword=terms.get((keyword.id, market.country_code), keyword.keyword),
                country=market.country_code,
            )
            for keyword in sorted(board.keywords, key=lambda item: item.position)
            if keyword_ids is None or keyword.id in keyword_ids
            for market in sorted(board.markets, key=lambda item: item.position)
            if countries is None or market.country_code in countries
        ]
    if not targets:
        return NicheCheckResult(searches=0, failures=0)

    owned_client = client or AppleSearchClient(
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
        request_delay=settings.request_delay,
        result_limit=settings.result_limit,
    )
    semaphore = asyncio.Semaphore(settings.concurrency)

    async def search(
        target: NicheSearchTarget,
    ) -> tuple[NicheSearchTarget, SearchOutcome | Exception]:
        async with semaphore:
            try:
                return target, await owned_client.search(
                    target.keyword,
                    target.country,
                    "iphone",
                )
            except AppleClientError as exc:
                return target, exc

    async with owned_client:
        results = await asyncio.gather(*(search(target) for target in targets))

    failures = 0
    with session_scope() as session:
        for target, outcome in results:
            if isinstance(outcome, Exception):
                failures += 1
                upsert_niche_metric(
                    session,
                    keyword_id=target.keyword_id,
                    country=target.country,
                    device="iphone",
                    volume=None,
                    difficulty=None,
                    sample_size=0,
                    status="error",
                    error=str(outcome),
                )
                continue
            estimates = estimate_keyword(outcome.response.results)
            upsert_niche_metric(
                session,
                keyword_id=target.keyword_id,
                country=target.country,
                device="iphone",
                volume=estimates.volume,
                difficulty=estimates.difficulty,
                sample_size=estimates.sample_size,
                status="success",
            )
        board = session.scalar(select(NicheBoard).where(NicheBoard.id == board_id))
        if board is not None:
            board.updated_at = datetime.now(UTC)
    return NicheCheckResult(searches=len(targets), failures=failures)


def refresh_niche_metrics(
    board_id: int,
    settings: Settings,
    *,
    client: AppleSearchClient | None = None,
    keyword_ids: set[int] | None = None,
    countries: set[str] | None = None,
) -> NicheCheckResult:
    """Synchronous entry point for the dashboard HTTP server."""

    return asyncio.run(
        refresh_niche_metrics_async(
            board_id,
            settings,
            client=client,
            keyword_ids=keyword_ids,
            countries=countries,
        )
    )
