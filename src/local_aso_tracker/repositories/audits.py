"""Persistence and JSON payloads for locally generated app audits."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.models import (
    App,
    AppleAdsSuggestion,
    AuditCountryResult,
    AuditFinding,
    AuditKeyword,
    AuditRun,
    CompetitorApp,
    Keyword,
    RankTopApp,
    Storefront,
    TrackingTarget,
)
from local_aso_tracker.services.keyword_popularity import popularity_opportunity

ACTIVE_AUDIT_STATUSES = {"queued", "running"}
AUDIT_PROMPT_VERSION = "audit-v3-specialist-pipeline"


def create_audit_run(
    session: Session,
    *,
    app_id: int,
    scope: str,
    country_code: str | None,
    device: str,
    provider: str,
    country_codes: Iterable[str],
) -> AuditRun:
    normalized_countries = list(dict.fromkeys(country_codes))
    if (
        scope != "country"
        or country_code is None
        or len(normalized_countries) != 1
        or normalized_countries[0] != country_code
    ):
        raise ValueError("audit runs must target exactly one country")
    run = AuditRun(
        app_id=app_id,
        scope=scope,
        country_code=country_code,
        device=device,
        provider=provider,
        status="queued",
        prompt_version=AUDIT_PROMPT_VERSION,
    )
    for code in normalized_countries:
        run.countries.append(
            AuditCountryResult(
                country_code=code,
                status="queued",
            )
        )
    session.add(run)
    session.flush()
    return run


def active_audit_run(
    session: Session,
    *,
    app_id: int,
    device: str,
    country_code: str | None = None,
) -> AuditRun | None:
    query = _run_query().where(
        AuditRun.app_id == app_id,
        AuditRun.device == device,
        AuditRun.status.in_(ACTIVE_AUDIT_STATUSES),
        AuditRun.scope == "country",
        AuditRun.prompt_version == AUDIT_PROMPT_VERSION,
    )
    if country_code is not None:
        query = query.where(AuditRun.country_code == country_code)
    return session.scalar(query.order_by(AuditRun.created_at.desc(), AuditRun.id.desc()).limit(1))


def get_audit_run(session: Session, run_id: int) -> AuditRun | None:
    return session.scalar(_run_query().where(AuditRun.id == run_id))


def latest_audit_run(
    session: Session,
    app_id: int,
    *,
    country_code: str | None = None,
    device: str | None = None,
) -> AuditRun | None:
    query = _run_query().where(
        AuditRun.app_id == app_id,
        AuditRun.scope == "country",
        AuditRun.prompt_version == AUDIT_PROMPT_VERSION,
    )
    if country_code is not None:
        query = query.where(AuditRun.country_code == country_code)
    if device is not None:
        query = query.where(AuditRun.device == device)
    return session.scalar(query.order_by(AuditRun.created_at.desc(), AuditRun.id.desc()).limit(1))


def recent_audit_runs(
    session: Session,
    app_id: int,
    *,
    limit: int = 6,
    country_code: str | None = None,
    device: str | None = None,
) -> list[AuditRun]:
    query = _run_query().where(
        AuditRun.app_id == app_id,
        AuditRun.scope == "country",
        AuditRun.prompt_version == AUDIT_PROMPT_VERSION,
    )
    if country_code is not None:
        query = query.where(AuditRun.country_code == country_code)
    if device is not None:
        query = query.where(AuditRun.device == device)
    return list(
        session.scalars(query.order_by(AuditRun.created_at.desc(), AuditRun.id.desc()).limit(limit))
    )


def audit_dashboard_payload(
    session: Session,
    *,
    app_id: int,
    run_id: int | None = None,
    country_code: str | None = None,
    device: str | None = None,
) -> dict[str, object]:
    storefront_names = {
        code: name
        for code, name in session.execute(
            select(Storefront.country_code, Storefront.display_name).where(
                Storefront.active.is_(True)
            )
        )
    }
    runs = recent_audit_runs(
        session,
        app_id,
        country_code=country_code,
        device=device,
    )
    selected = get_audit_run(session, run_id) if run_id is not None else (runs[0] if runs else None)
    if selected is not None and selected.app_id != app_id:
        raise ValueError("audit does not belong to the selected app")
    if selected is not None and selected.prompt_version != AUDIT_PROMPT_VERSION:
        raise ValueError("this audit uses a retired language policy; rerun it")
    if selected is not None and country_code is not None and selected.country_code != country_code:
        raise ValueError("audit does not belong to the selected country")
    if selected is not None and device is not None and selected.device != device:
        raise ValueError("audit does not belong to the selected device")
    return {
        "appId": app_id,
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "scope": run.scope,
                "country": run.country_code,
                "device": run.device,
                "provider": run.provider,
                "score": run.score,
                "createdAt": _iso(run.created_at),
                "completedAt": _iso(run.completed_at),
            }
            for run in runs
        ],
        "run": _run_payload(selected, storefront_names) if selected is not None else None,
        "latestByCountry": [
            {
                "id": run.id,
                "status": run.status,
                "country": run.country_code,
                "countryName": storefront_names.get(
                    run.country_code or "", (run.country_code or "").upper()
                ),
                "device": run.device,
                "provider": run.provider,
                "score": run.score,
                "createdAt": _iso(run.created_at),
                "completedAt": _iso(run.completed_at),
            }
            for run in latest_audit_runs_by_country(session, app_id)
        ],
    }


def latest_audit_runs_by_country(session: Session, app_id: int) -> list[AuditRun]:
    """The newest current-policy run for each storefront and device, for an overview."""

    latest: dict[tuple[str | None, str], AuditRun] = {}
    query = _run_query().where(
        AuditRun.app_id == app_id,
        AuditRun.scope == "country",
        AuditRun.prompt_version == AUDIT_PROMPT_VERSION,
    )
    for run in session.scalars(query.order_by(AuditRun.created_at.desc(), AuditRun.id.desc())):
        latest.setdefault((run.country_code, run.device), run)
    return sorted(latest.values(), key=lambda run: (run.country_code or "", run.device))


def add_audit_finding(
    session: Session,
    country: AuditCountryResult,
    *,
    position: int,
    tone: str,
    category: str,
    title: str,
    detail: str,
    terms: Iterable[str] = (),
) -> AuditFinding:
    finding = AuditFinding(
        audit_country_result_id=country.id,
        position=position,
        tone=tone[:20],
        category=category[:50],
        title=title[:255],
        detail=detail,
        terms=json.dumps(list(dict.fromkeys(terms)), ensure_ascii=False),
    )
    session.add(finding)
    return finding


def add_audit_keyword(
    session: Session,
    country: AuditCountryResult,
    *,
    keyword: str,
    normalized_keyword: str,
    intent: str = "",
    rationale: str = "",
) -> AuditKeyword:
    item = AuditKeyword(
        audit_country_result_id=country.id,
        keyword=keyword[:255],
        normalized_keyword=normalized_keyword[:255],
        intent=intent[:255],
        rationale=rationale,
        status="pending",
    )
    session.add(item)
    session.flush()
    return item


def _run_query() -> Select[tuple[AuditRun]]:
    return select(AuditRun).options(
        selectinload(AuditRun.countries).selectinload(AuditCountryResult.findings),
        selectinload(AuditRun.countries).selectinload(AuditCountryResult.keywords),
    )


def _run_payload(run: AuditRun, storefront_names: dict[str, str]) -> dict[str, object]:
    countries = sorted(run.countries, key=lambda item: item.country_code)
    completed = sum(item.status in {"success", "partial"} for item in countries)
    return {
        "id": run.id,
        "appId": run.app.apple_app_id if run.app is not None else None,
        "scope": run.scope,
        "country": run.country_code,
        "device": run.device,
        "provider": run.provider,
        "status": run.status,
        "score": run.score,
        "promptVersion": run.prompt_version,
        "createdAt": _iso(run.created_at),
        "startedAt": _iso(run.started_at),
        "completedAt": _iso(run.completed_at),
        "error": run.error_message,
        "progress": {
            "completed": completed,
            "total": len(countries),
        },
        "countries": [
            _country_payload(country, storefront_names.get(country.country_code))
            for country in countries
        ],
    }


def _country_payload(
    country: AuditCountryResult,
    display_name: str | None,
) -> dict[str, object]:
    findings = sorted(country.findings, key=lambda item: (item.position, item.id))
    ordered = sorted(country.keywords, key=lambda item: item.id)
    keywords = [item for item in ordered if item.channel != "apple_ads"]
    paid = [item for item in ordered if item.channel == "apple_ads"]
    keyword_lookup = {item.normalized_keyword: item for item in keywords}
    return {
        "id": country.id,
        "code": country.country_code,
        "name": display_name or country.country_code.upper(),
        "status": country.status,
        "score": country.score,
        "rankingScore": country.ranking_score,
        "listingScore": country.listing_score,
        "localizationScore": country.localization_score,
        "competitionScore": country.competition_score,
        "summary": country.summary,
        "error": country.error_message,
        "startedAt": _iso(country.started_at),
        "completedAt": _iso(country.completed_at),
        "findings": [
            _finding_payload(finding, country.country_code, keyword_lookup) for finding in findings
        ],
        "keywords": [
            {
                "id": keyword.id,
                "keyword": keyword.keyword,
                "intent": keyword.intent,
                "rationale": keyword.rationale,
                "rank": keyword.rank,
                "found": keyword.found,
                "resultLimit": keyword.result_limit,
                "volume": keyword.volume_estimate,
                "difficulty": keyword.difficulty_estimate,
                "popularity": keyword.apple_popularity,
                "popularityStatus": keyword.popularity_status,
                "opportunity": popularity_opportunity(
                    keyword.apple_popularity,
                    keyword.difficulty_estimate,
                    rank=keyword.rank,
                    found=bool(keyword.found),
                ),
                "sampleSize": keyword.sample_size,
                "checkedAt": _iso(keyword.checked_at),
                "status": keyword.status,
                "error": keyword.error_message,
            }
            for keyword in keywords
        ],
        # Searches for other apps' names: Apple Ads keywords, never listing copy.
        "paidKeywords": sorted(
            (
                {
                    "keyword": keyword.keyword,
                    "brandOwner": keyword.brand_owner,
                    "rank": keyword.rank,
                    "found": keyword.found,
                    "resultLimit": keyword.result_limit,
                    "popularity": keyword.apple_popularity,
                    "popularityStatus": keyword.popularity_status,
                    "status": keyword.status,
                }
                for keyword in paid
            ),
            key=lambda item: (
                item["popularity"] is None,
                -int(item["popularity"] or 0),
                str(item["keyword"]).casefold(),
            ),
        ),
    }


def _finding_payload(
    finding: AuditFinding,
    country_code: str,
    keyword_lookup: dict[str, AuditKeyword],
) -> dict[str, object]:
    terms = _terms(finding.terms)
    title = finding.title
    detail = finding.detail
    tone = finding.tone
    if title == "Recommended phrases are outside the current result window":
        title = "No recommended phrase placed the app in Apple's results"
        tone = "warning"
        detail = (
            f"The app was not found in the retrieved {country_code.upper()} result window "
            "for these phrases. This is a ranking result, not a measure of overall "
            "astrology interest."
        )
    if title.endswith("is already visible") and terms:
        keyword = keyword_lookup.get(" ".join(terms[0].casefold().split()))
        rank = keyword.rank if keyword is not None else None
        if rank is not None:
            local = country_code.upper()
            if rank <= 10:
                title = f"“{terms[0]}” ranks in the Top 10"
                tone = "positive"
                detail = (
                    f"It appears at #{rank} in {local}. Protect the position with "
                    "aligned listing metadata."
                )
            elif rank <= 50:
                title = f"“{terms[0]}” ranks in the Top 50"
                tone = "positive"
                detail = (
                    f"It appears at #{rank} in {local}. It is discoverable but not yet "
                    "in the Top 10; use it as a supporting phrase."
                )
            else:
                title = f"“{terms[0]}” is present outside the Top 50"
                tone = "info"
                detail = (
                    f"It appears at #{rank} in {local}. It is inside Apple's retrieved "
                    "window but is not a strong ranking yet; treat it as a longer-term "
                    "opportunity."
                )
    return {
        "position": finding.position,
        "tone": tone,
        "category": finding.category,
        "title": title,
        "detail": detail,
        "terms": terms,
    }


def _terms(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def discovery_terms(
    session: Session,
    *,
    app_id: int,
    country: str,
    suggestion_limit: int = 40,
) -> dict[str, list[str]]:
    """Terms with a known link to this app and market, to ground keyword discovery.

    ``tracked`` and ``audited`` come from this app's own work; ``suggested`` are the
    related searches Apple Ads returned for the app in this market.
    """

    code = country.lower()
    tracked = list(
        session.scalars(
            select(Keyword.keyword)
            .join(TrackingTarget, TrackingTarget.keyword_id == Keyword.id)
            .join(Storefront, TrackingTarget.storefront_id == Storefront.id)
            .where(
                TrackingTarget.app_id == app_id,
                TrackingTarget.active.is_(True),
                Storefront.country_code == code,
            )
            .distinct()
        )
    )
    audited = list(
        session.scalars(
            select(AuditKeyword.keyword)
            .join(AuditCountryResult, AuditKeyword.audit_country_result_id == AuditCountryResult.id)
            .join(AuditRun, AuditCountryResult.audit_run_id == AuditRun.id)
            .where(AuditRun.app_id == app_id, AuditCountryResult.country_code == code)
            .distinct()
        )
    )
    suggested = list(
        session.scalars(
            select(AppleAdsSuggestion.text)
            .where(
                AppleAdsSuggestion.app_id == app_id,
                AppleAdsSuggestion.country_or_region == code.upper(),
            )
            .order_by(AppleAdsSuggestion.id)
            .limit(suggestion_limit)
        )
    )
    return {"tracked": tracked, "audited": audited, "suggested": suggested}


def catalog_app_names(session: Session) -> list[tuple[int, str]]:
    """(App Store ID, name) of every app seen locally.

    Sources: Apple's top results from rank checks, competitor columns, and own apps.
    """

    rows: dict[int, str] = {}
    for track_id, name in session.execute(select(RankTopApp.track_id, RankTopApp.name)):
        rows.setdefault(int(track_id), name)
    for app_id, name in session.execute(select(CompetitorApp.apple_app_id, CompetitorApp.name)):
        rows.setdefault(int(app_id), name)
    for app_id, name in session.execute(select(App.apple_app_id, App.name)):
        rows.setdefault(int(app_id), name)
    return list(rows.items())


INTERRUPTED_MESSAGE = "Interrupted: the app closed before this audit finished."
_FINAL_STATUSES = {"success", "partial", "error", "cancelled"}


def mark_interrupted_runs(session: Session) -> int:
    """Close audits left queued or running by a previous process; returns how many.

    Audit workers are threads of the dashboard process, so after a restart nothing
    will ever finish these runs. They are marked as errors the user can rerun.
    """

    now = datetime.now(UTC)
    runs = list(session.scalars(select(AuditRun).where(AuditRun.status.in_(("queued", "running")))))
    for run in runs:
        run.status = "error"
        run.error_message = INTERRUPTED_MESSAGE
        run.completed_at = now
        for country in run.countries:
            if country.status not in _FINAL_STATUSES:
                country.status = "error"
                country.error_message = INTERRUPTED_MESSAGE
                country.completed_at = now
    return len(runs)
