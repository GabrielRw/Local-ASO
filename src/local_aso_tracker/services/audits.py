"""Local app audits: agent keyword research plus transparent Apple evidence."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from local_aso_tracker.apple.client import AppleClientError, AppleSearchClient, extract_rank
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
from local_aso_tracker.config import (
    Settings,
    load_settings,
)
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import (
    AuditCountryResult,
    ListingMetadata,
    Storefront,
)
from local_aso_tracker.repositories.audits import (
    add_audit_finding,
    add_audit_keyword,
    catalog_app_names,
    discovery_terms,
    get_audit_run,
)
from local_aso_tracker.repositories.data import (
    latest_pairs,
    list_targets,
    normalize_keyword,
)
from local_aso_tracker.services.agent import (
    AgentError,
    AuditKeywordSuggestion,
    AuditLocalizationResult,
    AuditMarketSuggestion,
    AuditSynthesisResult,
    generate_audit_keywords,
    generate_audit_localization_review,
    generate_audit_synthesis,
)
from local_aso_tracker.services.competitor_brands import BrandIndex, squash
from local_aso_tracker.services.coverage import (
    TrackedKeyword,
    analyze_distribution_strategy,
    analyze_listing_coverage,
)
from local_aso_tracker.services.estimates import estimate_keyword
from local_aso_tracker.services.keyword_popularity import (
    POPULARITY_FLOOR,
    PopularityReading,
    measure_keywords,
    popularity_opportunity,
)
from local_aso_tracker.services.localization_targets import COUNTRY_PRIMARY_LANGUAGE

logger = logging.getLogger(__name__)
# Apple Ads popularity at or above this is clear demand for an App Store query; most
# niche phrases sit at Apple's floor of 5.
HIGH_POPULARITY = 20
# Competitor-brand searches checked per market for the Apple Ads list.
MAX_BRAND_TERMS = 12


def _popularity_phrase(popularity: int) -> str:
    if popularity <= POPULARITY_FLOOR:
        return f"Apple Ads popularity at its floor ({POPULARITY_FLOOR}, too few searches to rank)"
    return f"Apple Ads popularity {popularity}/100"


FLOOR_FINDING_SUFFIX = "have too few searches to score"


def _keep_demand_warning(
    findings: list[CountryFinding], rule_findings: list[CountryFinding]
) -> list[CountryFinding]:
    """Keep the Apple-floor warning even when the editor's findings fill every slot.

    The editor ranks its own findings first, which would otherwise hide the one signal
    that says most proposed phrases have no measurable demand.
    """

    warning = next(
        (item for item in rule_findings if item.title.endswith(FLOOR_FINDING_SUFFIX)), None
    )
    if warning is None or any(item.title.endswith(FLOOR_FINDING_SUFFIX) for item in findings):
        return findings
    return [*findings[:5], warning]


def _opportunity_sort_key(item: KeywordEvidence) -> tuple[int, int, int, int]:
    """Measured Apple opportunity first, then the ratings-based fallback ordering."""

    return (
        0 if item.opportunity is not None else 1,
        -(item.opportunity or 0),
        -(item.volume or 0) if item.opportunity is None else 0,
        item.difficulty if item.difficulty is not None else 101,
    )


@dataclass(frozen=True)
class KeywordEvidence:
    keyword: str
    intent: str
    rationale: str
    rank: int | None
    found: bool
    result_limit: int
    volume: int | None
    difficulty: int | None
    sample_size: int
    status: str
    error: str | None
    popularity: int | None = None
    popularity_status: str | None = None
    # Set for a search of another app's name: an Apple Ads keyword, never listing copy.
    brand_owner: str | None = None

    @property
    def opportunity(self) -> int | None:
        """Apple popularity still to win, discounted by difficulty and current rank."""

        return popularity_opportunity(
            self.popularity, self.difficulty, rank=self.rank, found=self.found
        )

    @property
    def above_popularity_floor(self) -> bool:
        return self.popularity is not None and self.popularity > POPULARITY_FLOOR


@dataclass(frozen=True)
class CountryFinding:
    tone: str
    category: str
    title: str
    detail: str
    terms: list[str]


@dataclass(frozen=True)
class CountryAudit:
    country: str
    status: str
    score: int | None
    ranking_score: int | None
    listing_score: int | None
    localization_score: int | None
    competition_score: int | None
    summary: str | None
    keywords: list[KeywordEvidence]
    findings: list[CountryFinding]
    error: str | None = None
    paid_keywords: list[KeywordEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class AuditContext:
    app: dict[str, object]
    apple_app_id: int
    markets: list[dict[str, str]]
    market_context: dict[str, dict[str, object]]
    tracked_by_country: dict[str, list[dict[str, object]]]
    device: str
    app_db_id: int = 0


class AuditError(RuntimeError):
    """An audit could not be completed."""


class AuditRunner:
    """Execute one queued audit without blocking the dashboard request thread."""

    def __init__(
        self,
        *,
        agent_runner: Callable[..., tuple[str, dict[str, AuditMarketSuggestion]]] | None = None,
        localization_runner: Callable[..., tuple[str, AuditLocalizationResult]] | None = None,
        synthesis_runner: Callable[..., tuple[str, AuditSynthesisResult]] | None = None,
        listing_loader: Callable[..., AppleListing] | None = None,
        apple_client_factory: Callable[[Settings], AppleSearchClient] | None = None,
        popularity_measurer: Callable[[list[str], str], dict[str, PopularityReading]] | None = None,
    ) -> None:
        self._agent_runner = agent_runner or generate_audit_keywords
        self._localization_runner = localization_runner or generate_audit_localization_review
        self._synthesis_runner = synthesis_runner or generate_audit_synthesis
        self._listing_loader = listing_loader or lookup_listing
        self._apple_client_factory = apple_client_factory
        self._popularity_measurer = popularity_measurer or measure_keywords

    def _with_popularity(
        self, evidence: list[KeywordEvidence], country: str
    ) -> list[KeywordEvidence]:
        """Attach Apple Ads popularity where it exists; never fail the audit over it."""

        try:
            readings = self._popularity_measurer(
                [item.keyword for item in evidence if item.status == "success"], country
            )
        except Exception as exc:
            logger.warning("Apple Ads popularity skipped for audit market %s: %s", country, exc)
            return evidence
        enriched: list[KeywordEvidence] = []
        for item in evidence:
            try:
                reading = readings.get(normalize_keyword(item.keyword))
            except ValueError:
                reading = None
            enriched.append(
                replace(item, popularity=reading.popularity, popularity_status=reading.status)
                if reading is not None
                else item
            )
        return enriched

    def _brand_index(self, apple_app_id: int) -> BrandIndex:
        with session_scope() as session:
            return BrandIndex(catalog_app_names(session), exclude_ids=[apple_app_id])

    def _market_demand(
        self, app_id: int, country: str, brands: BrandIndex
    ) -> tuple[dict[str, object] | None, list[str]]:
        """Discovery signals plus the competitor-brand searches Apple suggested.

        Brand searches are kept out of the signals so the agent is not nudged toward
        names it may not put in a listing; they are returned for the Apple Ads list.
        """

        with session_scope() as session:
            terms = discovery_terms(session, app_id=app_id, country=country)
        brand_terms = [keyword for keyword in terms["suggested"] if brands.owner(keyword)]
        brand_keys = {squash(keyword) for keyword in brand_terms}
        terms = {
            source: [keyword for keyword in values if squash(keyword) not in brand_keys]
            for source, values in terms.items()
        }
        return self._demand_signals(terms, country), brand_terms

    def _demand_signals(
        self, terms: dict[str, list[str]], country: str
    ) -> dict[str, object] | None:
        """Apple Ads popularity for terms tied to this app, to steer keyword discovery.

        Returns ``None`` when nothing has been measured (for example without Apple Ads),
        so discovery prompts stay unchanged for users who have not set it up.
        """

        candidates = list(
            dict.fromkeys([*terms["tracked"], *terms["audited"], *terms["suggested"]])
        )
        if not candidates:
            return None
        try:
            readings = self._popularity_measurer(candidates, country)
        except Exception as exc:
            logger.warning("Apple Ads demand signals skipped for %s: %s", country, exc)
            return None

        def measured(source: list[str]) -> list[tuple[str, int]]:
            values: list[tuple[str, int]] = []
            for keyword in source:
                try:
                    reading = readings.get(normalize_keyword(keyword))
                except ValueError:
                    continue
                if reading is not None and reading.popularity is not None:
                    values.append((keyword, reading.popularity))
            return values

        own = measured([*terms["tracked"], *terms["audited"]])
        suggested = measured(terms["suggested"])
        if not own and not suggested:
            return None
        searched = sorted(
            {
                keyword: value for keyword, value in [*own, *suggested] if value > POPULARITY_FLOOR
            }.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
        floor = [keyword for keyword, value in own if value <= POPULARITY_FLOOR]
        return {
            "scale": (
                "applePopularity is Apple Ads' 5-100 popularity for the exact typed query; "
                f"{POPULARITY_FLOOR} is the floor (too few searches to rank)."
            ),
            "searchedQueries": [
                {"keyword": keyword, "applePopularity": value} for keyword, value in searched[:20]
            ],
            "floorQueries": floor[:15],
            "appleRelatedSearches": [keyword for keyword, _ in suggested][:25],
        }

    @staticmethod
    def _split_brands(
        candidates: list[AuditKeywordSuggestion], brands: BrandIndex
    ) -> tuple[list[AuditKeywordSuggestion], list[str]]:
        listing: list[AuditKeywordSuggestion] = []
        brand_terms: list[str] = []
        for candidate in candidates:
            if brands.owner(candidate.keyword):
                brand_terms.append(candidate.keyword)
            else:
                listing.append(candidate)
        return listing, brand_terms

    def _check_brand_terms(
        self,
        terms: Iterable[str],
        brands: BrandIndex,
        *,
        country: str,
        apple_app_id: int,
        device: str,
        settings: Settings,
        skip: Iterable[str] = (),
    ) -> list[KeywordEvidence]:
        """Rank-check and measure competitor-brand searches for the Apple Ads list."""

        # Deduplicate on the typed query, not the squashed brand: Apple scores spellings
        # separately ("costar" 56, "co star" 5), so both are worth bidding on.
        seen = {" ".join(keyword.split()).casefold() for keyword in skip}
        suggestions: list[AuditKeywordSuggestion] = []
        owners: dict[str, str] = {}
        for keyword in terms:
            key = " ".join(keyword.split()).casefold()
            owner = brands.owner(keyword)
            if owner is None or key in seen:
                continue
            seen.add(key)
            owners[keyword] = owner
            suggestions.append(
                AuditKeywordSuggestion(
                    keyword=keyword,
                    intent="Competitor brand search",
                    rationale=(
                        f"People search for {owner}. App Store rules forbid another app's "
                        "name in your listing, so reach this audience with Apple Ads."
                    ),
                )
            )
            if len(suggestions) >= MAX_BRAND_TERMS:
                break
        if not suggestions:
            return []
        evidence = asyncio.run(
            self._check_candidates(suggestions, country, apple_app_id, device, settings)
        )
        return self._with_popularity(
            [replace(item, brand_owner=owners.get(item.keyword)) for item in evidence], country
        )

    def run(self, run_id: int, cancel_event: threading.Event | None = None) -> None:
        stop = cancel_event or threading.Event()
        try:
            self._run(run_id, stop)
        except Exception as exc:
            logger.exception("Audit run %s failed", run_id)
            with session_scope() as session:
                run = get_audit_run(session, run_id)
                if run is not None:
                    run.status = "cancelled" if stop.is_set() else "error"
                    run.error_message = str(exc)[:1000]
                    run.completed_at = datetime.now(UTC)
                    for country in run.countries:
                        if country.status in {
                            "queued",
                            "running",
                            "analyzing",
                            "localizing",
                            "checking",
                            "synthesizing",
                        }:
                            country.status = "cancelled" if stop.is_set() else "error"
                            country.error_message = str(exc)[:1000]
                            country.completed_at = datetime.now(UTC)

    def _run(self, run_id: int, stop: threading.Event) -> None:
        settings = load_settings()
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None or run.status == "cancelled":
                return
            run.status = "running"
            run.started_at = run.started_at or datetime.now(UTC)
        context = self._load_context(run_id, stop)
        if stop.is_set():
            self._mark_cancelled(run_id)
            return
        base_facts_by_country = {
            country: self._audit_facts(
                country=country,
                market=context.market_context.get(country, {}),
                tracked=context.tracked_by_country.get(country, []),
            )
            for country in context.tracked_by_country.keys() | set(context.market_context)
        }
        requested_provider = self._provider_for_run(run_id)
        brands = self._brand_index(context.apple_app_id)
        demand: dict[str, dict[str, object]] = {}
        brand_terms_by_country: dict[str, list[str]] = {}
        for country in sorted(context.market_context):
            signals, suggested_brands = self._market_demand(context.app_db_id, country, brands)
            brand_terms_by_country[country] = suggested_brands
            if signals is not None:
                demand[country] = signals
        discovery_context = {**context.app, "demandSignals": demand} if demand else context.app
        provider, generated = self._agent_runner(
            app_context=discovery_context,
            markets=context.markets,
            provider=requested_provider,
            codex_path=settings.agent_codex_path,
            claude_path=settings.agent_claude_path,
            timeout=settings.agent_timeout,
        )
        if stop.is_set():
            self._mark_cancelled(run_id)
            return
        candidates_by_country = {country: market.keywords for country, market in generated.items()}
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                return
            run.provider = provider
            run.started_at = run.started_at or datetime.now(UTC)
            for country_row in run.countries:
                country_row.started_at = datetime.now(UTC)
                if country_row.country_code in candidates_by_country:
                    country_row.status = "localizing"
                else:
                    country_row.status = "error"
                    country_row.error_message = (
                        "The local agent returned no keywords for this market."
                    )
                    country_row.completed_at = datetime.now(UTC)

        localization_by_country: dict[str, AuditLocalizationResult] = {}
        for country in list(candidates_by_country):
            if stop.is_set():
                self._mark_cancelled(run_id)
                return
            facts = base_facts_by_country.get(country, [])
            market = context.market_context.get(country, {})
            language = self._market_language(country, market)
            try:
                _review_provider, review = self._localization_runner(
                    audit_context=context.app,
                    country=country,
                    language=language,
                    facts=facts,
                    allowed_terms=self._allowed_terms(
                        candidates_by_country[country],
                        context.tracked_by_country.get(country, []),
                        facts,
                    ),
                    provider=provider,
                    codex_path=settings.agent_codex_path,
                    claude_path=settings.agent_claude_path,
                    timeout=settings.agent_timeout,
                )
            except AgentError as exc:
                logger.warning(
                    "Localization specialist failed for audit %s (%s): %s",
                    run_id,
                    country,
                    exc,
                )
            else:
                localization_by_country[country] = review
                candidates_by_country[country] = self._merge_candidates(
                    candidates_by_country[country],
                    review.candidate_phrases,
                )

        for country in list(candidates_by_country):
            listing_candidates, agent_brands = self._split_brands(
                candidates_by_country[country], brands
            )
            candidates_by_country[country] = listing_candidates
            brand_terms_by_country[country] = [
                *agent_brands,
                *brand_terms_by_country.get(country, []),
            ]

        evidences_by_country: dict[str, list[KeywordEvidence]] = {}
        paid_by_country: dict[str, list[KeywordEvidence]] = {}
        for country, candidates in candidates_by_country.items():
            if stop.is_set():
                self._mark_cancelled(run_id)
                return
            with session_scope() as session:
                audit_country = self._country_row(session, run_id, country)
                if audit_country is not None:
                    audit_country.status = "checking"
                    audit_country.started_at = audit_country.started_at or datetime.now(UTC)
            evidences_by_country[country] = self._with_popularity(
                asyncio.run(
                    self._check_candidates(
                        candidates,
                        country,
                        context.apple_app_id,
                        context.device,
                        settings,
                    )
                ),
                country,
            )
            paid_by_country[country] = self._check_brand_terms(
                brand_terms_by_country.get(country, []),
                brands,
                country=country,
                apple_app_id=context.apple_app_id,
                device=context.device,
                settings=settings,
            )

        for country, country_result in self._build_country_results(
            context,
            candidates_by_country,
            evidences_by_country,
            localization_by_country,
        ):
            if stop.is_set():
                self._mark_cancelled(run_id)
                return
            with session_scope() as session:
                audit_country = self._country_row(session, run_id, country)
                if audit_country is not None:
                    audit_country.status = "synthesizing"
            country_result = replace(country_result, paid_keywords=paid_by_country.get(country, []))
            country_result = self._synthesized_country_result(
                context=context,
                result=country_result,
                evidence=evidences_by_country.get(country, []),
                localization_review=localization_by_country.get(country),
                provider=provider,
                settings=settings,
            )
            self._persist_country_result(run_id, country_result)

        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                return
            completed = [
                item.score
                for item in run.countries
                if item.score is not None and item.status in {"success", "partial"}
            ]
            run.score = round(sum(completed) / len(completed)) if completed else None
            statuses = {item.status for item in run.countries}
            run.status = "success" if statuses == {"success"} else "partial"
            run.completed_at = datetime.now(UTC)
            if not completed:
                run.status = "error"
                run.error_message = "No audit country returned a score."

    def expand_country(
        self,
        run_id: int,
        country: str,
        instruction: str,
    ) -> int:
        """Ask the local agent for another country-specific discovery round."""

        country = country.strip().lower()
        instruction = " ".join(instruction.split())
        if len(country) != 2 or not instruction:
            raise ValueError("country and discovery instruction are required")
        settings = load_settings()
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                raise AuditError(f"unknown audit run: {run_id}")
            if run.status in {"queued", "running"}:
                raise AuditError("wait for the current audit to finish before expanding it")
            country_result = next(
                (item for item in run.countries if item.country_code == country),
                None,
            )
            if country_result is None:
                raise AuditError(f"{country.upper()} is not part of this audit")
            app = run.app
            metadata = session.scalar(
                select(ListingMetadata)
                .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
                .where(
                    ListingMetadata.app_id == app.id,
                    Storefront.country_code == country,
                )
            )
            targets = list_targets(
                session,
                apple_id=app.apple_app_id,
                country=country,
                device=run.device,
                active_only=True,
            )
            pairs = latest_pairs(session, targets)
            tracked: list[dict[str, object]] = [
                {
                    "keyword": target.keyword.keyword,
                    "rank": pairs[target.id][0].rank if target.id in pairs else None,
                    "found": pairs[target.id][0].found if target.id in pairs else False,
                }
                for target in targets
            ]
            listing_rows = [item for item in country_result.keywords if item.channel != "apple_ads"]
            paid_rows = [item for item in country_result.keywords if item.channel == "apple_ads"]
            existing = [
                AuditKeywordSuggestion(
                    keyword=item.keyword,
                    intent=item.intent,
                    rationale=item.rationale,
                )
                for item in listing_rows
            ]
            existing_paid = [
                KeywordEvidence(
                    keyword=item.keyword,
                    intent=item.intent,
                    rationale=item.rationale,
                    rank=item.rank,
                    found=bool(item.found),
                    result_limit=item.result_limit or settings.result_limit,
                    volume=item.volume_estimate,
                    difficulty=item.difficulty_estimate,
                    sample_size=item.sample_size or 0,
                    status=item.status,
                    error=item.error_message,
                    popularity=item.apple_popularity,
                    popularity_status=item.popularity_status,
                    brand_owner=item.brand_owner,
                )
                for item in paid_rows
            ]
            existing_evidence = [
                KeywordEvidence(
                    keyword=item.keyword,
                    intent=item.intent,
                    rationale=item.rationale,
                    rank=item.rank,
                    found=bool(item.found),
                    result_limit=item.result_limit or settings.result_limit,
                    volume=item.volume_estimate,
                    difficulty=item.difficulty_estimate,
                    sample_size=item.sample_size or 0,
                    status=item.status,
                    error=item.error_message,
                    popularity=item.apple_popularity,
                    popularity_status=item.popularity_status,
                )
                for item in listing_rows
            ]
            market_context: dict[str, dict[str, object]] = {
                country: {
                    "name": country.upper(),
                    "language": COUNTRY_PRIMARY_LANGUAGE.get(country, "English"),
                    "savedMetadata": (
                        {
                            "name": metadata.name,
                            "subtitle": metadata.subtitle,
                            "keywords": metadata.keyword_field,
                            "goal": metadata.channel_goal,
                            "brandTerm": metadata.brand_term,
                        }
                        if metadata is not None
                        else None
                    ),
                    "trackedKeywords": tracked,
                }
            }
            app_context = {
                "name": app.name,
                "appleAppId": app.apple_app_id,
                "trackedKeywords": {country: tracked},
                "previousAuditKeywords": {country: [item.keyword for item in listing_rows]},
            }
            markets = [
                {
                    "country": country,
                    "name": country.upper(),
                    "language": COUNTRY_PRIMARY_LANGUAGE.get(country, "English"),
                }
            ]
            apple_app_id = app.apple_app_id
            app_db_id = app.id
            device = run.device

        brands = self._brand_index(apple_app_id)
        signals, suggested_brands = self._market_demand(app_db_id, country, brands)
        if signals is not None:
            app_context["demandSignals"] = {country: signals}
        listings = self._load_public_listings(
            apple_app_id,
            [country],
            settings=settings,
            stop=threading.Event(),
        )
        if country in listings:
            listing = listings[country]
            market_context[country]["publicListing"] = {
                "name": listing.track_name,
                "genre": listing.genre,
                "description": " ".join(listing.description.split())[:2_000],
                "languageCodes": listing.language_codes,
            }
        facts = self._audit_facts(
            country=country,
            market=market_context[country],
            tracked=tracked,
        )
        requested_provider = self._provider_for_run(run_id)
        localization_review: AuditLocalizationResult | None = None
        try:
            _review_provider, localization_review = self._localization_runner(
                audit_context=app_context,
                country=country,
                language=self._market_language(country, market_context[country]),
                facts=facts,
                allowed_terms=self._allowed_terms(existing, tracked, facts),
                provider=requested_provider,
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
                timeout=settings.agent_timeout,
            )
        except AgentError as exc:
            logger.warning(
                "Localization specialist failed while expanding audit %s (%s): %s",
                run_id,
                country,
                exc,
            )
        provider, generated = self._agent_runner(
            app_context=app_context,
            markets=markets,
            provider=requested_provider,
            codex_path=settings.agent_codex_path,
            claude_path=settings.agent_claude_path,
            timeout=settings.agent_timeout,
            instruction=instruction,
        )
        market = generated.get(country)
        if market is None:
            raise AuditError(f"the local agent returned no new {country.upper()} keywords")
        new_candidates = self._merge_candidates(
            market.keywords,
            localization_review.candidate_phrases if localization_review else [],
            blocked=[item.keyword for item in existing],
        )
        new_candidates, agent_brands = self._split_brands(new_candidates, brands)
        new_paid = self._check_brand_terms(
            [*agent_brands, *suggested_brands],
            brands,
            country=country,
            apple_app_id=apple_app_id,
            device=device,
            settings=settings,
            skip=[item.keyword for item in existing_paid],
        )
        if not new_candidates and not new_paid:
            raise AuditError("the local agent returned only keywords already in this audit")
        new_evidence = asyncio.run(
            self._check_candidates(
                new_candidates,
                country,
                apple_app_id,
                device,
                settings,
            )
        )
        context = AuditContext(
            app=app_context,
            apple_app_id=apple_app_id,
            markets=markets,
            market_context=market_context,
            tracked_by_country={country: tracked},
            device=device,
            app_db_id=app_db_id,
        )
        evidence = self._with_popularity(existing_evidence + new_evidence, country)
        candidates = existing + new_candidates
        result = next(
            (
                item
                for _, item in self._build_country_results(
                    context,
                    {country: candidates},
                    {country: evidence},
                    {country: localization_review} if localization_review else {},
                )
            ),
            None,
        )
        if result is None:
            raise AuditError("the expanded audit could not be scored")
        result = replace(result, paid_keywords=[*existing_paid, *new_paid])
        result = self._synthesized_country_result(
            context=context,
            result=result,
            evidence=evidence,
            localization_review=localization_review,
            provider=provider,
            settings=settings,
        )
        self._persist_country_result(run_id, result)
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is not None:
                scores = [
                    item.score
                    for item in run.countries
                    if item.score is not None and item.status in {"success", "partial"}
                ]
                run.score = round(sum(scores) / len(scores)) if scores else None
                statuses = {item.status for item in run.countries}
                run.status = "success" if statuses == {"success"} else "partial"
                run.completed_at = datetime.now(UTC)
                run.provider = provider
        return len(new_evidence) + len(new_paid)

    def _load_context(self, run_id: int, stop: threading.Event) -> AuditContext:
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                raise AuditError(f"unknown audit run: {run_id}")
            if run.status == "cancelled":
                raise AuditError("audit was cancelled")
            app = run.app
            country_rows = sorted(run.countries, key=lambda item: item.country_code)
            country_codes = [item.country_code for item in country_rows]
            storefront_names: dict[str, str] = {
                code: name
                for code, name in session.execute(
                    select(Storefront.country_code, Storefront.display_name).where(
                        Storefront.country_code.in_(country_codes)
                    )
                ).all()
            }
            metadata_rows = session.execute(
                select(ListingMetadata, Storefront.country_code)
                .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
                .where(ListingMetadata.app_id == app.id)
            ).all()
            metadata_by_country = {country: metadata for metadata, country in metadata_rows}
            apple_app_id = app.apple_app_id
            app_db_id = app.id
            device = run.device
            targets = list_targets(
                session,
                apple_id=app.apple_app_id,
                device=run.device,
                active_only=True,
            )
            pairs = latest_pairs(session, targets)
            tracked_by_country: dict[str, list[dict[str, object]]] = {}
            for target in targets:
                code = target.storefront.country_code
                pair = pairs.get(target.id)
                tracked_by_country.setdefault(code, []).append(
                    {
                        "keyword": target.keyword.keyword,
                        "rank": pair[0].rank if pair else None,
                        "found": pair[0].found if pair else False,
                    }
                )
            market_context: dict[str, dict[str, object]] = {}
            for row in country_rows:
                metadata = metadata_by_country.get(row.country_code)
                market_context[row.country_code] = {
                    "name": storefront_names.get(row.country_code, row.country_code.upper()),
                    "language": COUNTRY_PRIMARY_LANGUAGE.get(
                        row.country_code,
                        "English",
                    ),
                    "savedMetadata": (
                        {
                            "name": metadata.name,
                            "subtitle": metadata.subtitle,
                            "keywords": metadata.keyword_field,
                            "goal": metadata.channel_goal,
                            "brandTerm": metadata.brand_term,
                        }
                        if metadata is not None
                        else None
                    ),
                    "trackedKeywords": tracked_by_country.get(row.country_code, []),
                }
            app_context: dict[str, object] = {
                "name": app.name,
                "appleAppId": app.apple_app_id,
                "trackedKeywords": tracked_by_country,
            }
            markets = [
                {
                    "country": row.country_code,
                    "name": storefront_names.get(row.country_code, row.country_code.upper()),
                    "language": COUNTRY_PRIMARY_LANGUAGE.get(
                        row.country_code,
                        "English",
                    ),
                }
                for row in country_rows
            ]

        listings = self._load_public_listings(
            apple_app_id,
            country_codes,
            settings=load_settings(),
            stop=stop,
        )
        for country, listing in listings.items():
            market_context[country]["publicListing"] = {
                "name": listing.track_name,
                "genre": listing.genre,
                "description": " ".join(listing.description.split())[:2_000],
                "languageCodes": listing.language_codes,
            }
        return AuditContext(
            app=app_context,
            apple_app_id=apple_app_id,
            markets=markets,
            market_context=market_context,
            tracked_by_country=tracked_by_country,
            device=device,
            app_db_id=app_db_id,
        )

    def _load_public_listings(
        self,
        app_id: int,
        country_codes: list[str],
        *,
        settings: Settings,
        stop: threading.Event,
    ) -> dict[str, AppleListing]:
        if not app_id or not country_codes:
            return {}
        results: dict[str, AppleListing] = {}

        def load(country: str) -> tuple[str, AppleListing | None]:
            if stop.is_set():
                return country, None
            try:
                return country, self._listing_loader(
                    app_id,
                    country,
                    timeout=settings.request_timeout,
                    retry_count=settings.retry_count,
                )
            except AppleClientError:
                logger.debug("Could not load audit listing for %s", country)
                return country, None

        workers = max(1, min(settings.concurrency, len(country_codes), 6))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="local-aso-audit-list",
        ) as pool:
            futures = [pool.submit(load, country) for country in country_codes]
            for future in as_completed(futures):
                country, listing = future.result()
                if listing is not None:
                    results[country] = listing
        return results

    async def _check_candidates(
        self,
        candidates: Iterable[AuditKeywordSuggestion],
        country: str,
        apple_app_id: int,
        device: str,
        settings: Settings,
    ) -> list[KeywordEvidence]:
        semaphore = asyncio.Semaphore(settings.concurrency)
        client = (
            self._apple_client_factory(settings)
            if self._apple_client_factory is not None
            else AppleSearchClient(
                timeout=settings.request_timeout,
                retry_count=settings.retry_count,
                request_delay=settings.request_delay,
                result_limit=settings.result_limit,
            )
        )

        async def check(candidate: AuditKeywordSuggestion) -> KeywordEvidence:
            async with semaphore:
                try:
                    outcome = await client.search(
                        candidate.keyword,
                        country,
                        device,
                    )
                except AppleClientError as exc:
                    return KeywordEvidence(
                        keyword=candidate.keyword,
                        intent=candidate.intent,
                        rationale=candidate.rationale,
                        rank=None,
                        found=False,
                        result_limit=settings.result_limit,
                        volume=None,
                        difficulty=None,
                        sample_size=0,
                        status="error",
                        error=str(exc),
                    )
                estimates = estimate_keyword(outcome.response.results)
                rank = extract_rank(outcome.response, apple_app_id)
                return KeywordEvidence(
                    keyword=candidate.keyword,
                    intent=candidate.intent,
                    rationale=candidate.rationale,
                    rank=rank.rank,
                    found=rank.found,
                    result_limit=settings.result_limit,
                    volume=estimates.volume,
                    difficulty=estimates.difficulty,
                    sample_size=estimates.sample_size,
                    status="success",
                    error=None,
                )

        async with client:
            return await asyncio.gather(*(check(candidate) for candidate in candidates))

    def _synthesized_country_result(
        self,
        *,
        context: AuditContext,
        result: CountryAudit,
        evidence: list[KeywordEvidence],
        localization_review: AuditLocalizationResult | None,
        provider: str,
        settings: Settings,
    ) -> CountryAudit:
        if result.status == "error":
            return result
        facts = self._audit_facts(
            country=result.country,
            market=context.market_context.get(result.country, {}),
            tracked=context.tracked_by_country.get(result.country, []),
            evidence=evidence,
            findings=result.findings,
        )
        try:
            _provider, synthesis = self._synthesis_runner(
                audit_context=context.app,
                country=result.country,
                language=self._market_language(
                    result.country,
                    context.market_context.get(result.country, {}),
                ),
                facts=facts,
                localization_review=localization_review,
                evidence=[
                    self._keyword_evidence_payload(index, item)
                    for index, item in enumerate(evidence, start=1)
                ],
                allowed_terms=self._allowed_terms(
                    evidence,
                    context.tracked_by_country.get(result.country, []),
                    facts,
                ),
                provider=provider,
                codex_path=settings.agent_codex_path,
                claude_path=settings.agent_claude_path,
                timeout=settings.agent_timeout,
            )
        except AgentError as exc:
            logger.warning(
                "Audit editor failed for %s (%s): %s",
                result.country,
                provider,
                exc,
            )
            return replace(result, findings=result.findings[:6])
        synthesized_findings = [
            CountryFinding(
                tone=finding.tone,
                category=finding.category,
                title=finding.title,
                detail=finding.detail,
                terms=finding.terms,
            )
            for finding in synthesis.findings
        ]
        return replace(
            result,
            findings=_keep_demand_warning(
                self._dedupe_findings([*synthesized_findings, *result.findings])[:6],
                result.findings,
            ),
            summary=synthesis.summary,
        )

    @staticmethod
    def _market_language(country: str, market: dict[str, object]) -> str:
        return str(market.get("language") or COUNTRY_PRIMARY_LANGUAGE.get(country, "English"))

    def _audit_facts(
        self,
        *,
        country: str,
        market: dict[str, object],
        tracked: list[dict[str, object]],
        evidence: list[KeywordEvidence] | None = None,
        findings: list[CountryFinding] | None = None,
    ) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = [
            {
                "id": "market.context",
                "category": "workflow",
                "title": "Audit market",
                "detail": (
                    f"{country.upper()} uses {self._market_language(country, market)} "
                    "for this audit."
                ),
                "data": {
                    "country": country,
                    "name": market.get("name", country.upper()),
                    "language": self._market_language(country, market),
                },
                "terms": [],
            }
        ]
        metadata = market.get("savedMetadata")
        if isinstance(metadata, dict):
            metadata_data = {
                "name": str(metadata.get("name", "")),
                "subtitle": str(metadata.get("subtitle", "")),
                "keywords": str(metadata.get("keywords", "")),
                "goal": str(metadata.get("goal", "")),
                "brandTerm": str(metadata.get("brandTerm", "")),
            }
            facts.append(
                {
                    "id": "listing.saved_metadata",
                    "category": "listing",
                    "title": "Saved listing metadata",
                    "detail": "These are the locally saved indexed fields for this storefront.",
                    "data": metadata_data,
                    "terms": self._metadata_terms(metadata_data),
                }
            )
            try:
                strategy = analyze_distribution_strategy(
                    metadata_data["name"],
                    metadata_data["subtitle"],
                    metadata_data["keywords"],
                    goal=(
                        metadata_data["goal"]
                        if metadata_data["goal"] in {"aso_seo_aeo", "ugc_ads"}
                        else "aso_seo_aeo"
                    ),
                    brand_term=metadata_data["brandTerm"],
                )
            except ValueError:
                strategy = None
            if strategy is not None:
                facts.append(
                    {
                        "id": "metadata.repetition",
                        "category": "metadata",
                        "title": "Meaningful-word repetition",
                        "detail": strategy.no_repetition.detail,
                        "data": {
                            "passed": strategy.no_repetition.passed,
                            "duplicates": [
                                {
                                    "word": item.word,
                                    "total": item.total,
                                    "fields": item.fields,
                                }
                                for item in strategy.duplicate_words
                            ],
                        },
                        "terms": [item.word for item in strategy.duplicate_words],
                    }
                )
                facts.append(
                    {
                        "id": "metadata.title_order",
                        "category": "metadata",
                        "title": "Title strategy check",
                        "detail": strategy.title_order.detail,
                        "data": {
                            "passed": strategy.title_order.passed,
                            "goal": strategy.goal,
                            "brandTerm": strategy.brand_term,
                        },
                        "terms": [],
                    }
                )
        else:
            facts.append(
                {
                    "id": "listing.saved_metadata_missing",
                    "category": "localization",
                    "title": "Saved listing metadata is missing",
                    "detail": (
                        f"No name, subtitle, or keyword field has been saved for {country.upper()}."
                    ),
                    "data": {"country": country},
                    "terms": [],
                }
            )
        public_listing = market.get("publicListing")
        if isinstance(public_listing, dict):
            facts.append(
                {
                    "id": "listing.public_listing",
                    "category": "localization",
                    "title": "Public App Store listing",
                    "detail": "Public Apple listing fields returned for this storefront.",
                    "data": {
                        "name": str(public_listing.get("name", "")),
                        "genre": str(public_listing.get("genre", "")),
                        "languageCodes": public_listing.get("languageCodes", []),
                        "description": str(public_listing.get("description", ""))[:800],
                    },
                    "terms": [str(public_listing.get("name", ""))],
                }
            )
        top10 = [
            item
            for item in tracked
            if item.get("found") and int(str(item.get("rank") or 999)) <= 10
        ]
        facts.append(
            {
                "id": "visibility.tracked_summary",
                "category": "visibility",
                "title": "Tracked visibility summary",
                "detail": (
                    f"{len(top10)} of {len(tracked)} tracked keywords are in the Top 10."
                    if tracked
                    else "No active tracked keywords are available for this market."
                ),
                "data": {
                    "trackedCount": len(tracked),
                    "top10Count": len(top10),
                },
                "terms": [],
            }
        )
        for index, tracked_item in enumerate(tracked, start=1):
            facts.append(
                {
                    "id": f"tracked.{index}",
                    "category": "visibility",
                    "title": "Tracked keyword position",
                    "detail": (
                        f"{tracked_item.get('keyword', '')}: "
                        + (
                            f"rank #{tracked_item.get('rank')}"
                            if tracked_item.get("found") and tracked_item.get("rank")
                            else "outside or unavailable in the retrieved result window"
                        )
                    ),
                    "data": {
                        "keyword": str(tracked_item.get("keyword", "")),
                        "rank": tracked_item.get("rank"),
                        "found": bool(tracked_item.get("found")),
                    },
                    "terms": [str(tracked_item.get("keyword", ""))],
                }
            )
        if evidence:
            successful = [item for item in evidence if item.status == "success"]
            facts.append(
                {
                    "id": "keywords.summary",
                    "category": "opportunity",
                    "title": "Verified keyword evidence summary",
                    "detail": (
                        f"{sum(item.found for item in successful)} of "
                        f"{len(evidence)} checked phrases were found in Apple's retrieved "
                        "result window."
                    ),
                    "data": {
                        "checked": len(evidence),
                        "found": sum(item.found for item in successful),
                        "failed": sum(item.status == "error" for item in evidence),
                    },
                    "terms": [],
                }
            )
            for index, evidence_item in enumerate(evidence, start=1):
                facts.append(
                    {
                        **self._keyword_evidence_payload(index, evidence_item),
                        "title": "Verified Apple keyword evidence",
                        "detail": self._keyword_evidence_detail(evidence_item),
                        "terms": [evidence_item.keyword],
                    }
                )
        if findings:
            for index, finding in enumerate(findings, start=1):
                facts.append(
                    {
                        "id": f"finding.{index}",
                        "category": finding.category,
                        "title": finding.title,
                        "detail": finding.detail,
                        "data": {
                            "tone": finding.tone,
                            "terms": finding.terms,
                        },
                        "terms": finding.terms,
                    }
                )
        return facts

    @staticmethod
    def _keyword_evidence_payload(
        index: int,
        item: KeywordEvidence,
    ) -> dict[str, Any]:
        return {
            "id": f"keyword.{index}",
            "category": "opportunity" if item.found else "competition",
            "keyword": item.keyword,
            "intent": item.intent,
            "rationale": item.rationale,
            "rank": item.rank,
            "found": item.found,
            "resultLimit": item.result_limit,
            "volumeEstimate": item.volume,
            "difficultyEstimate": item.difficulty,
            "applePopularity": item.popularity,
            "applePopularityStatus": item.popularity_status,
            "opportunityScore": item.opportunity,
            "sampleSize": item.sample_size,
            "status": item.status,
            "error": item.error,
        }

    @staticmethod
    def _keyword_evidence_detail(item: KeywordEvidence) -> str:
        if item.status == "error":
            return f"{item.keyword}: Apple verification failed."
        position = (
            f"rank #{item.rank}"
            if item.found and item.rank is not None
            else f"outside the retrieved {item.result_limit}-result window"
        )
        estimates: list[str] = []
        if item.popularity is not None:
            estimates.append(_popularity_phrase(item.popularity))
        elif item.volume is not None:
            estimates.append(f"volume estimate {item.volume}/100")
        if item.difficulty is not None:
            estimates.append(f"difficulty estimate {item.difficulty}/100")
        suffix = f"; {', '.join(estimates)}" if estimates else ""
        return f"{item.keyword}: {position}{suffix}."

    @staticmethod
    def _metadata_terms(metadata: dict[str, str]) -> list[str]:
        values = [
            metadata.get("name", ""),
            metadata.get("subtitle", ""),
            *[
                item
                for item in metadata.get("keywords", "").replace("\n", ",").split(",")
                if item.strip()
            ],
        ]
        return list(dict.fromkeys(" ".join(item.split()) for item in values if item.strip()))

    @staticmethod
    def _allowed_terms(
        candidates: Iterable[AuditKeywordSuggestion | KeywordEvidence],
        tracked: list[dict[str, object]],
        facts: list[dict[str, Any]],
    ) -> list[str]:
        values = [
            item.keyword if isinstance(item, (AuditKeywordSuggestion, KeywordEvidence)) else ""
            for item in candidates
        ]
        values.extend(str(item.get("keyword", "")) for item in tracked)
        for fact in facts:
            raw_terms = fact.get("terms")
            if isinstance(raw_terms, list):
                values.extend(str(term) for term in raw_terms)
        return list(
            dict.fromkeys(
                " ".join(value.split())
                for value in values
                if isinstance(value, str) and value.strip()
            )
        )[:100]

    @staticmethod
    def _merge_candidates(
        primary: Iterable[AuditKeywordSuggestion],
        secondary: Iterable[AuditKeywordSuggestion],
        *,
        blocked: Iterable[str] = (),
        limit: int = 10,
    ) -> list[AuditKeywordSuggestion]:
        blocked_normalized = {normalize_keyword(value) for value in blocked if value.strip()}
        result: list[AuditKeywordSuggestion] = []
        seen = set(blocked_normalized)
        for candidate in [*primary, *secondary]:
            normalized = normalize_keyword(candidate.keyword)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(candidate)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _localization_findings(
        review: AuditLocalizationResult | None,
    ) -> list[CountryFinding]:
        if review is None:
            return []
        return [
            CountryFinding(
                tone=finding.tone,
                category=finding.category,
                title=finding.title,
                detail=finding.detail,
                terms=finding.terms,
            )
            for finding in review.findings
        ]

    @staticmethod
    def _dedupe_findings(findings: Iterable[CountryFinding]) -> list[CountryFinding]:
        result: list[CountryFinding] = []
        seen: set[str] = set()
        for finding in findings:
            key = " ".join(finding.title.split()).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(finding)
        return result

    def _build_country_results(
        self,
        context: AuditContext,
        candidates_by_country: dict[str, list[AuditKeywordSuggestion]],
        evidences_by_country: dict[str, list[KeywordEvidence]],
        localization_by_country: dict[str, AuditLocalizationResult] | None = None,
    ) -> list[tuple[str, CountryAudit]]:
        results: list[tuple[str, CountryAudit]] = []
        for country, candidates in candidates_by_country.items():
            evidence = evidences_by_country.get(country, [])
            if not evidence:
                results.append(
                    (
                        country,
                        CountryAudit(
                            country=country,
                            status="error",
                            score=None,
                            ranking_score=None,
                            listing_score=None,
                            localization_score=None,
                            competition_score=None,
                            summary=None,
                            keywords=[],
                            findings=[
                                CountryFinding(
                                    tone="warning",
                                    category="agent",
                                    title="No usable keywords were returned",
                                    detail=(
                                        "The local agent did not return a usable phrase set for "
                                        f"{country.upper()}. Check the provider and rerun "
                                        "the audit."
                                    ),
                                    terms=[],
                                )
                            ],
                            error="no usable keywords returned",
                        ),
                    )
                )
                continue
            market = context.market_context.get(country, {})
            metadata = market.get("savedMetadata")
            tracked = context.tracked_by_country.get(country, [])
            successful = [item for item in evidence if item.status == "success"]
            tracked_found = [item for item in tracked if item.get("found") and item.get("rank")]
            top10 = sum(int(str(item.get("rank") or 999)) <= 10 for item in tracked_found)
            ranking_score = round(100 * top10 / len(tracked)) if tracked else 0
            listing_score = self._listing_score(metadata, candidates)
            localization_score = self._localization_score(metadata, market)
            competition_values = [
                item.difficulty for item in successful if item.difficulty is not None
            ]
            competition_score = (
                round(100 - sum(competition_values) / len(competition_values))
                if competition_values
                else 0
            )
            score = round(
                0.40 * ranking_score
                + 0.30 * listing_score
                + 0.20 * localization_score
                + 0.10 * competition_score
            )
            deterministic_findings = self._findings(
                country=country,
                tracked=tracked,
                evidence=evidence,
                metadata=metadata,
                all_keywords=[item.keyword for item in evidence],
            )
            specialization_findings = self._localization_findings(
                localization_by_country.get(country)
                if localization_by_country is not None
                else None
            )
            findings = self._dedupe_findings([*specialization_findings, *deterministic_findings])[
                :12
            ]
            summary = (
                f"{country.upper()} scores {score}/100. "
                f"{top10} of {len(tracked)} tracked phrases rank in the Top 10; "
                f"{sum(item.found for item in successful)} of {len(evidence)} recommended "
                "phrases were found in Apple's result window."
            )
            failed = any(item.status == "error" for item in evidence)
            results.append(
                (
                    country,
                    CountryAudit(
                        country=country,
                        status="partial" if failed else "success",
                        score=score,
                        ranking_score=ranking_score,
                        listing_score=listing_score,
                        localization_score=localization_score,
                        competition_score=competition_score,
                        summary=summary,
                        keywords=evidence,
                        findings=findings,
                    ),
                )
            )
        return results

    def _persist_country_result(self, run_id: int, result: CountryAudit) -> None:
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                return
            country = next(
                (item for item in run.countries if item.country_code == result.country),
                None,
            )
            if country is None:
                return
            country.status = result.status
            country.score = result.score
            country.ranking_score = result.ranking_score
            country.listing_score = result.listing_score
            country.localization_score = result.localization_score
            country.competition_score = result.competition_score
            country.summary = result.summary
            country.error_message = result.error
            country.completed_at = datetime.now(UTC)
            country.findings.clear()
            country.keywords.clear()
            session.flush()
            for position, finding in enumerate(result.findings, start=1):
                add_audit_finding(
                    session,
                    country,
                    position=position,
                    tone=finding.tone,
                    category=finding.category,
                    title=finding.title,
                    detail=finding.detail,
                    terms=finding.terms,
                )
            stored: set[str] = set()
            for evidence, channel in [
                *((item, "aso") for item in result.keywords),
                *((item, "apple_ads") for item in result.paid_keywords),
            ]:
                normalized = normalize_keyword(evidence.keyword)
                if normalized in stored:
                    continue
                stored.add(normalized)
                keyword = add_audit_keyword(
                    session,
                    country,
                    keyword=evidence.keyword,
                    normalized_keyword=normalized,
                    intent=evidence.intent,
                    rationale=evidence.rationale,
                )
                keyword.channel = channel
                keyword.brand_owner = evidence.brand_owner
                keyword.rank = evidence.rank
                keyword.found = evidence.found
                keyword.result_limit = evidence.result_limit
                keyword.volume_estimate = evidence.volume
                keyword.apple_popularity = evidence.popularity
                keyword.popularity_status = evidence.popularity_status
                keyword.difficulty_estimate = evidence.difficulty
                keyword.sample_size = evidence.sample_size
                keyword.checked_at = datetime.now(UTC)
                keyword.status = evidence.status
                keyword.error_message = evidence.error

    def _mark_cancelled(self, run_id: int) -> None:
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is None:
                return
            run.status = "cancelled"
            run.completed_at = datetime.now(UTC)
            for country in run.countries:
                if country.status in {
                    "queued",
                    "running",
                    "analyzing",
                    "localizing",
                    "checking",
                    "synthesizing",
                }:
                    country.status = "cancelled"
                    country.completed_at = datetime.now(UTC)

    def _provider_for_run(self, run_id: int) -> str:
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            return run.provider if run is not None else "auto"

    @staticmethod
    def _country_row(
        session: Any,
        run_id: int,
        country: str,
    ) -> AuditCountryResult | None:
        run = get_audit_run(session, run_id)
        return (
            next(
                (item for item in run.countries if item.country_code == country),
                None,
            )
            if run is not None
            else None
        )

    @staticmethod
    def _listing_score(
        metadata: object,
        candidates: list[AuditKeywordSuggestion],
    ) -> int:
        if not isinstance(metadata, dict):
            return 0
        tracked = [
            TrackedKeyword(
                keyword=candidate.keyword,
                rank=None,
                found=False,
                result_limit=200,
            )
            for candidate in candidates
        ]
        coverage = analyze_listing_coverage(
            str(metadata.get("name", "")),
            str(metadata.get("subtitle", "")),
            str(metadata.get("keywords", "")),
            tracked,
        )
        return round(100 * coverage.tracked_matches / len(candidates)) if candidates else 0

    @staticmethod
    def _localization_score(metadata: object, market: dict[str, object]) -> int:
        if not isinstance(metadata, dict):
            return 0
        has_name = bool(str(metadata.get("name", "")).strip())
        has_subtitle = bool(str(metadata.get("subtitle", "")).strip())
        has_keywords = bool(str(metadata.get("keywords", "")).strip())
        if has_name and has_subtitle and has_keywords:
            return 100
        if has_name and (has_subtitle or has_keywords):
            return 65
        if has_name:
            return 35
        listing = market.get("publicListing")
        if isinstance(listing, dict) and listing.get("languageCodes"):
            return 20
        return 0

    @staticmethod
    def _findings(
        *,
        country: str,
        tracked: list[dict[str, object]],
        evidence: list[KeywordEvidence],
        metadata: object,
        all_keywords: list[str],
    ) -> list[CountryFinding]:
        findings: list[CountryFinding] = []
        local = country.upper()
        if not isinstance(metadata, dict):
            findings.append(
                CountryFinding(
                    tone="warning",
                    category="localization",
                    title="Local listing metadata is missing",
                    detail=(
                        f"Add the {local} name, subtitle, and keyword field in the listing "
                        "audit so recommendations can be checked against what the storefront "
                        "actually displays."
                    ),
                    terms=[],
                )
            )
        else:
            if not str(metadata.get("subtitle", "")).strip():
                findings.append(
                    CountryFinding(
                        tone="danger",
                        category="listing",
                        title="The subtitle is empty",
                        detail=f"The {local} listing has no subtitle saved for intent alignment.",
                        terms=[],
                    )
                )
            try:
                strategy = analyze_distribution_strategy(
                    str(metadata.get("name", "")),
                    str(metadata.get("subtitle", "")),
                    str(metadata.get("keywords", "")),
                    goal=(
                        str(metadata.get("goal", ""))
                        if metadata.get("goal") in {"aso_seo_aeo", "ugc_ads"}
                        else "aso_seo_aeo"
                    ),
                    brand_term=str(metadata.get("brandTerm", "")),
                )
            except ValueError:
                strategy = None
            if strategy is not None and strategy.duplicate_words:
                repeated_terms = [item.word for item in strategy.duplicate_words[:4]]
                findings.append(
                    CountryFinding(
                        tone="warning",
                        category="metadata",
                        title="The indexed fields repeat meaningful words",
                        detail=(
                            f"{strategy.no_repetition.detail} Reallocate the freed characters "
                            "to verified phrases that are not already covered."
                        ),
                        terms=repeated_terms,
                    )
                )
            if (
                strategy is not None
                and str(metadata.get("brandTerm", "")).strip()
                and strategy.title_order.passed is False
            ):
                findings.append(
                    CountryFinding(
                        tone="danger",
                        category="listing",
                        title="The title does not follow the selected strategy",
                        detail=strategy.title_order.detail,
                        terms=[str(metadata.get("name", ""))],
                    )
                )
            if not str(metadata.get("keywords", "")).strip():
                findings.append(
                    CountryFinding(
                        tone="danger",
                        category="listing",
                        title="The keyword field is empty",
                        detail=(
                            f"The {local} audit has no keyword field to compare with search intent."
                        ),
                        terms=[],
                    )
                )
        if tracked:
            top10 = [
                item
                for item in tracked
                if item.get("found") and int(str(item.get("rank") or 999)) <= 10
            ]
            if top10:
                findings.append(
                    CountryFinding(
                        tone="positive",
                        category="visibility",
                        title=f"{len(top10)} tracked phrases are in the Top 10",
                        detail=(
                            f"Protect the strongest {local} positions with aligned title, "
                            "subtitle, and keyword-field coverage."
                        ),
                        terms=[str(item.get("keyword", "")) for item in top10[:4]],
                    )
                )
            else:
                findings.append(
                    CountryFinding(
                        tone="warning",
                        category="visibility",
                        title="No tracked phrase is currently in the Top 10",
                        detail=(
                            f"Use the recommended phrases to find a realistic entry point "
                            f"in {local}."
                        ),
                        terms=[str(item.get("keyword", "")) for item in tracked[:4]],
                    )
                )
        successful = [item for item in evidence if item.status == "success"]
        quick_wins = [
            item
            for item in successful
            if item.found and item.rank is not None and 10 < item.rank <= 30
        ]
        if quick_wins:
            # Prefer quick wins people actually search for: a #12 at Apple's floor is
            # worth less than a #25 with real popularity.
            ranked_quick_wins = sorted(
                quick_wins, key=lambda item: (*_opportunity_sort_key(item), item.rank or 101)
            )
            best_quick_win = ranked_quick_wins[0]
            demand = (
                f" {_popularity_phrase(best_quick_win.popularity)}; opportunity score "
                f"{best_quick_win.opportunity}."
                if best_quick_win.popularity is not None and best_quick_win.opportunity is not None
                else ""
            )
            findings.append(
                CountryFinding(
                    tone="info",
                    category="opportunity",
                    title=f"“{best_quick_win.keyword}” is close to the Top 10",
                    detail=(
                        f"It ranks #{best_quick_win.rank} in {local}.{demand} This is a "
                        "nearer-term push opportunity than a phrase outside the retrieved "
                        "result window."
                    ),
                    terms=[item.keyword for item in ranked_quick_wins[:3]],
                )
            )
        # A gap is a phrase the app does not rank for (or ranks beyond #50). With Apple
        # Ads popularity it must clear a real demand bar; without it, fall back to the
        # ratings-based volume estimate.
        high_demand_gaps = [
            item
            for item in successful
            if (not item.found or (item.rank or 0) > 50)
            and (
                (item.popularity is not None and item.popularity >= HIGH_POPULARITY)
                or (
                    item.popularity_status is None and item.volume is not None and item.volume >= 45
                )
            )
        ]
        if high_demand_gaps:
            ranked_gaps = sorted(high_demand_gaps, key=_opportunity_sort_key)
            gap = ranked_gaps[0]
            position = (
                f"ranked #{gap.rank}"
                if gap.found and gap.rank is not None
                else f"was outside the retrieved {gap.result_limit}-result window"
            )
            if gap.popularity is not None:
                evidence_text = _popularity_phrase(gap.popularity)
                if gap.difficulty is not None:
                    evidence_text += (
                        f", difficulty estimate {gap.difficulty}/100, opportunity score "
                        f"{gap.opportunity}"
                    )
                reason = f"Apple reports real demand ({evidence_text})"
            else:
                estimates = [f"volume estimate {gap.volume}/100"]
                if gap.difficulty is not None:
                    estimates.append(f"difficulty estimate {gap.difficulty}/100")
                reason = f"Its ratings-based {' and '.join(estimates)} suggest demand"
            findings.append(
                CountryFinding(
                    tone="warning",
                    category="opportunity",
                    title=f"High-demand phrase gap: “{gap.keyword}”",
                    detail=(
                        f"The app {position} in {local} for this phrase. {reason}, which "
                        "makes it worth a focused listing experiment."
                    ),
                    terms=[item.keyword for item in ranked_gaps[:3]],
                )
            )
        measured = [item for item in successful if item.popularity_status == "measured"]
        floor_phrases = [item for item in measured if not item.above_popularity_floor]
        if measured and len(floor_phrases) >= max(2, len(measured) // 2):
            findings.append(
                CountryFinding(
                    tone="info",
                    category="competition",
                    title=(
                        f"{len(floor_phrases)} of {len(measured)} checked phrases "
                        f"{FLOOR_FINDING_SUFFIX}"
                    ),
                    detail=(
                        f"Apple Ads rates them at its floor of {POPULARITY_FLOOR} in {local}. "
                        "They can still convert, but keyword-field characters are better spent "
                        "on phrases Apple scores above the floor."
                    ),
                    terms=[item.keyword for item in floor_phrases[:4]],
                )
            )
        found = [item for item in successful if item.found]
        if found:
            best = sorted(found, key=lambda item: item.rank or 999)[0]
            rank = best.rank or 999
            if rank <= 10:
                title = f"“{best.keyword}” ranks in the Top 10"
                tone = "positive"
                detail = (
                    f"It appears at #{rank} in {local}. Protect the position with aligned "
                    "listing metadata."
                )
            elif rank <= 50:
                title = f"“{best.keyword}” ranks in the Top 50"
                tone = "positive"
                detail = (
                    f"It appears at #{rank} in {local}. It is discoverable but not yet in "
                    "the Top 10; use it as a supporting phrase."
                )
            else:
                title = f"“{best.keyword}” is present outside the Top 50"
                tone = "info"
                detail = (
                    f"It appears at #{rank} in {local}. It is inside Apple's retrieved "
                    "window but is not a strong ranking yet; treat it as a longer-term "
                    "opportunity."
                )
            findings.append(
                CountryFinding(
                    tone=tone,
                    category="opportunity",
                    title=title,
                    detail=detail,
                    terms=[best.keyword],
                )
            )
        else:
            findings.append(
                CountryFinding(
                    tone="warning",
                    category="opportunity",
                    title="No recommended phrase placed the app in Apple's results",
                    detail=(
                        f"The app was not found in the retrieved {local} result window for "
                        "these phrases. This is a ranking result, not a measure of overall "
                        "interest in the topic."
                    ),
                    terms=[item.keyword for item in successful[:4]],
                )
            )
        difficult = [item for item in successful if item.difficulty is not None]
        if difficult:
            easiest = sorted(difficult, key=lambda item: item.difficulty or 101)[:2]
            findings.append(
                CountryFinding(
                    tone="info",
                    category="competition",
                    title="A few phrases have a lower competition estimate",
                    detail=(
                        f"Use the transparent ratings-based estimate as a triage signal, "
                        f"not as a guaranteed {local} ranking forecast."
                    ),
                    terms=[item.keyword for item in easiest],
                )
            )
        if len(findings) < 3:
            findings.append(
                CountryFinding(
                    tone="info",
                    category="workflow",
                    title="Review the phrase set before adding it",
                    detail=(
                        "The local agent proposed the phrases; Apple supplied the ranking and "
                        "estimate evidence. Validate the wording in your own listing workflow."
                    ),
                    terms=all_keywords[:4],
                )
            )
        return _keep_demand_warning(findings[:6], findings)


class AuditWorker:
    """Run audit jobs in daemon threads and support cancellation by run ID."""

    def __init__(self, runner: AuditRunner | None = None) -> None:
        self.runner = runner or AuditRunner()
        self._events: dict[int, threading.Event] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self, run_id: int) -> None:
        with self._lock:
            existing = self._threads.get(run_id)
            if existing is not None and existing.is_alive():
                return
            event = threading.Event()
            thread = threading.Thread(
                target=self._execute,
                args=(run_id, event),
                name=f"local-aso-audit-{run_id}",
                daemon=True,
            )
            self._events[run_id] = event
            self._threads[run_id] = thread
            thread.start()

    def cancel(self, run_id: int) -> None:
        with self._lock:
            event = self._events.get(run_id)
            if event is not None:
                event.set()
        with session_scope() as session:
            run = get_audit_run(session, run_id)
            if run is not None and run.status in {"queued", "running"}:
                run.status = "cancelled"
                run.completed_at = datetime.now(UTC)
                for country in run.countries:
                    if country.status in {
                        "queued",
                        "running",
                        "analyzing",
                        "localizing",
                        "checking",
                        "synthesizing",
                    }:
                        country.status = "cancelled"
                        country.completed_at = datetime.now(UTC)

    def stop(self, timeout: float = 3.0) -> None:
        with self._lock:
            events = list(self._events.values())
            threads = list(self._threads.values())
        for event in events:
            event.set()
        for thread in threads:
            thread.join(timeout=timeout)

    def _execute(self, run_id: int, event: threading.Event) -> None:
        try:
            self.runner.run(run_id, event)
        finally:
            with self._lock:
                self._events.pop(run_id, None)
                self._threads.pop(run_id, None)
