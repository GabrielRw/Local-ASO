"""Localized App Store listing generation, review, and App Store Connect push."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.apple.app_store_connect import (
    AppStoreConnectClient,
    AppStoreConnectError,
    AppStoreConnectLocalization,
    connection_status,
)
from local_aso_tracker.apple.listing import lookup_listing
from local_aso_tracker.config import Settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import (
    App,
    ListingLocalizationDraft,
    ListingMetadata,
    Storefront,
)
from local_aso_tracker.repositories.audits import latest_audit_run
from local_aso_tracker.repositories.listing_localizations import (
    add_localization_iteration,
    approve_localization_draft,
    draft_public_payload,
    get_main_localization_country,
    list_localization_drafts,
    record_push_event,
    save_main_localization_country,
    upsert_localization_draft,
)
from local_aso_tracker.services.agent import generate_listing_localization
from local_aso_tracker.services.coverage import analyze_distribution_strategy
from local_aso_tracker.services.localization_targets import (
    APP_STORE_LOCALE_LANGUAGE,
    COUNTRY_PRIMARY_LANGUAGE,
    app_store_locale_for_country,
)

LISTING_FIELDS = (
    "name",
    "subtitle",
    "keywords",
    "description",
    "promotionalText",
    "whatsNew",
)
LISTING_LIMITS = {
    "name": (2, 30),
    "subtitle": (0, 30),
    "keywords": (0, 100),
    "description": (0, 4_000),
    "promotionalText": (0, 170),
    "whatsNew": (0, 4_000),
}
MAX_LOCALIZATION_ITERATIONS = 3


@dataclass(frozen=True)
class ListingSource:
    country: str
    locale: str
    language: str
    fields: dict[str, str]
    mode: str
    app_info_id: str | None = None
    version_id: str | None = None
    version_state: str | None = None


@dataclass(frozen=True)
class ListingGenerationResult:
    drafts: list[dict[str, object]]
    iterations: int


def listing_localization_studio(
    session: Session,
    *,
    app_id: int,
    current_country: str,
    settings: Settings,
) -> dict[str, object]:
    app = session.scalar(select(App).where(App.apple_app_id == app_id))
    if app is None:
        raise ValueError(f"unknown app ID: {app_id}")
    main_country = (get_main_localization_country(session, app.id) or current_country).lower()
    countries = list(
        session.scalars(
            select(Storefront).where(Storefront.active.is_(True)).order_by(Storefront.display_name)
        )
    )
    metadata = session.scalar(
        select(ListingMetadata)
        .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
        .where(
            ListingMetadata.app_id == app.id,
            Storefront.country_code == main_country,
        )
    )
    drafts = list_localization_drafts(session, app_id=app.id)
    draft_by_locale = {draft.target_locale: draft_public_payload(draft) for draft in drafts}
    source_locale = app_store_locale_for_country(main_country)
    return {
        "appId": app_id,
        "bundleId": app.bundle_id,
        "mainCountry": main_country,
        "sourceLocale": source_locale,
        "sourceLanguage": APP_STORE_LOCALE_LANGUAGE.get(
            source_locale,
            COUNTRY_PRIMARY_LANGUAGE.get(main_country, "English"),
        ),
        "sourceFields": {
            "name": metadata.name if metadata is not None else app.name,
            "subtitle": metadata.subtitle if metadata is not None else "",
            "keywords": metadata.keyword_field if metadata is not None else "",
            "description": "",
            "promotionalText": "",
            "whatsNew": "",
        },
        "connection": connection_status(settings),
        "countries": [_localization_country(storefront, main_country) for storefront in countries],
        "drafts": [draft_by_locale[locale] for locale in sorted(draft_by_locale)],
    }


def save_main_storefront(
    *,
    app_id: int,
    country: str,
) -> None:
    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {app_id}")
        storefront = session.scalar(select(Storefront).where(Storefront.country_code == country))
        if storefront is None or not storefront.active:
            raise ValueError(f"unknown active country: {country}")
        save_main_localization_country(
            session,
            app_id=app.id,
            country=country,
        )


def generate_localization_drafts(
    *,
    app_id: int,
    main_country: str,
    target_countries: list[str],
    provider: str,
    settings: Settings,
) -> ListingGenerationResult:
    main_country = main_country.strip().lower()
    targets = list(dict.fromkeys(country.strip().lower() for country in target_countries))
    if not targets:
        raise ValueError("select at least one target country")
    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {app_id}")
        # Drafts are generated locally; the bundle ID is only needed to push them.
        active_codes = set(
            session.scalars(select(Storefront.country_code).where(Storefront.active.is_(True)))
        )
        invalid = [country for country in [main_country, *targets] if country not in active_codes]
        if invalid:
            raise ValueError(f"unknown active country: {invalid[0]}")
        source_locale = app_store_locale_for_country(main_country)
        same_locale = [
            country for country in targets if app_store_locale_for_country(country) == source_locale
        ]
        if same_locale:
            raise ValueError(
                f"{same_locale[0].upper()} uses the same App Store locale as the main listing "
                f"({source_locale})"
            )
        save_main_localization_country(session, app_id=app.id, country=main_country)
        metadata = session.scalar(
            select(ListingMetadata)
            .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
            .where(
                ListingMetadata.app_id == app.id,
                Storefront.country_code == main_country,
            )
        )
        audit_keywords = _audit_keywords_for_targets(
            session,
            app_id=app.id,
            countries=targets,
        )
    source = _listing_source(
        app=app,
        main_country=main_country,
        metadata=metadata,
        settings=settings,
    )
    groups: dict[str, list[str]] = {}
    for country in targets:
        locale = app_store_locale_for_country(country)
        groups.setdefault(locale, []).append(country)
    created: list[dict[str, object]] = []
    total_iterations = 0
    for target_locale, countries in groups.items():
        target_language = APP_STORE_LOCALE_LANGUAGE.get(
            target_locale,
            COUNTRY_PRIMARY_LANGUAGE.get(countries[0], "English"),
        )
        fields, provider_used, validation, rounds = _generate_validated_fields(
            source=source,
            target_locale=target_locale,
            target_language=target_language,
            brand_term=metadata.brand_term if metadata is not None else "",
            goal=metadata.channel_goal if metadata is not None else "aso_seo_aeo",
            audit_keywords=audit_keywords,
            provider=provider,
            settings=settings,
        )
        total_iterations += rounds
        remote = _remote_localization_ids(
            app=app,
            target_locale=target_locale,
            settings=settings,
        )
        with session_scope() as session:
            db_app = session.scalar(select(App).where(App.apple_app_id == app_id))
            assert db_app is not None
            draft = upsert_localization_draft(
                session,
                app_id=db_app.id,
                source_country=main_country,
                source_locale=source.locale,
                target_locale=target_locale,
                target_countries=countries,
                language=target_language,
                provider=provider_used,
                source_fields=source.fields,
                fields=fields,
                validation=validation,
                iteration_count=rounds,
                remote_ids=remote,
            )
            history_items = validation.get("history", [])
            for number, item in enumerate(
                history_items if isinstance(history_items, list) else [],
                start=1,
            ):
                if not isinstance(item, dict):
                    continue
                add_localization_iteration(
                    session,
                    draft=draft,
                    iteration=number,
                    provider=str(item.get("provider") or provider_used),
                    fields=item.get("fields", {}) if isinstance(item.get("fields"), dict) else {},
                    validation=item.get("validation", {})
                    if isinstance(item.get("validation"), dict)
                    else {},
                )
            created.append(draft_public_payload(draft))
    return ListingGenerationResult(drafts=created, iterations=total_iterations)


def approve_localization(*, draft_id: int) -> dict[str, object]:
    with session_scope() as session:
        draft = session.get(ListingLocalizationDraft, draft_id)
        if draft is None:
            raise ValueError(f"unknown localization draft: {draft_id}")
        approve_localization_draft(session, draft)
        return draft_public_payload(draft)


def update_localization_fields(
    *,
    draft_id: int,
    fields: dict[str, str],
) -> dict[str, object]:
    with session_scope() as session:
        draft = session.get(ListingLocalizationDraft, draft_id)
        if draft is None:
            raise ValueError(f"unknown localization draft: {draft_id}")
        app = session.get(App, draft.app_id)
        if app is None:
            raise ValueError("localization draft app no longer exists")
        metadata = session.scalar(
            select(ListingMetadata)
            .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
            .where(
                ListingMetadata.app_id == app.id,
                Storefront.country_code == draft.source_country,
            )
        )
        normalized = {key: str(fields.get(key, "")).strip() for key in LISTING_FIELDS}
        validation = validate_listing_localization(
            normalized,
            source_fields=_json_object(draft.source_fields),
            brand_term=metadata.brand_term if metadata is not None else "",
            goal=metadata.channel_goal if metadata is not None else "aso_seo_aeo",
        )
        draft.fields = json.dumps(normalized, ensure_ascii=False)
        draft.validation = json.dumps(validation, ensure_ascii=False)
        draft.status = "needs_review"
        draft.error_message = None
        draft.approved_at = None
        draft.updated_at = datetime.now(UTC)
        add_localization_iteration(
            session,
            draft=draft,
            iteration=draft.iteration_count + 1,
            provider="manual",
            fields=normalized,
            validation=validation,
        )
        draft.iteration_count += 1
        session.flush()
        return draft_public_payload(draft)


def push_localization(
    *,
    draft_id: int,
    settings: Settings,
) -> dict[str, object]:
    with session_scope() as session:
        item = session.get(ListingLocalizationDraft, draft_id)
        if item is None:
            raise ValueError(f"unknown localization draft: {draft_id}")
        if item.status != "approved":
            raise ValueError("approve this localization before pushing it")
        app = session.get(App, item.app_id)
        if app is None or not app.bundle_id:
            raise ValueError(
                "this app's bundle ID isn't known yet; open it once with an internet "
                "connection so Apple's listing can supply it, then push again"
            )
        fields = _json_object(item.fields)
        source_fields = _json_object(item.source_fields)
        target_locale = item.target_locale
    with AppStoreConnectClient(settings) as client:
        try:
            result = client.push_localization(
                bundle_id=app.bundle_id,
                target_locale=target_locale,
                fields={key: str(fields.get(key, "")) for key in LISTING_FIELDS},
                preserved_fields={
                    key: str(source_fields.get(key, ""))
                    for key in (
                        "privacyPolicyUrl",
                        "privacyChoicesUrl",
                        "privacyPolicyText",
                        "supportUrl",
                        "marketingUrl",
                    )
                },
            )
        except AppStoreConnectError as exc:
            with session_scope() as session:
                item = session.get(ListingLocalizationDraft, draft_id)
                if item is not None:
                    record_push_event(
                        session,
                        draft=item,
                        status="failed",
                        fields=fields,
                        before_values={},
                        after_values=fields,
                        error=str(exc),
                    )
            raise
    with session_scope() as session:
        item = session.get(ListingLocalizationDraft, draft_id)
        if item is not None:
            app_info_id = result.get("appInfoLocalizationId")
            version_localization_id = result.get("versionLocalizationId")
            item.remote_app_info_localization_id = (
                str(app_info_id) if app_info_id is not None else None
            )
            item.remote_version_localization_id = (
                str(version_localization_id) if version_localization_id is not None else None
            )
            version_id = result.get("versionId")
            version_state = result.get("versionState")
            item.remote_version_id = str(version_id) if version_id is not None else None
            item.remote_version_state = str(version_state) if version_state is not None else None
            before_values = result.get("before")
            record_push_event(
                session,
                draft=item,
                status="success",
                fields=fields,
                before_values=before_values if isinstance(before_values, dict) else {},
                after_values=fields,
            )
            return draft_public_payload(item)
    raise ValueError("the localization draft disappeared during push")


def _generate_validated_fields(
    *,
    source: ListingSource,
    target_locale: str,
    target_language: str,
    brand_term: str,
    goal: str,
    audit_keywords: list[str],
    provider: str,
    settings: Settings,
) -> tuple[dict[str, str], str, dict[str, object], int]:
    previous_fields: dict[str, str] | None = None
    feedback: list[str] = []
    history: list[dict[str, object]] = []
    provider_used = provider
    fields: dict[str, str] = {}
    validation: dict[str, object] = {}
    for _iteration in range(1, MAX_LOCALIZATION_ITERATIONS + 1):
        provider_used, generated = generate_listing_localization(
            source_fields=source.fields,
            source_locale=source.locale,
            target_locale=target_locale,
            target_language=target_language,
            brand_term=brand_term,
            goal=goal,
            audit_keywords=audit_keywords,
            previous_fields=previous_fields,
            feedback=feedback,
            provider=provider,
            codex_path=settings.agent_codex_path,
            claude_path=settings.agent_claude_path,
            timeout=settings.agent_timeout,
        )
        generated_fields = generated.model_dump()
        fields = {key: str(generated_fields.get(key, "")).strip() for key in LISTING_FIELDS}
        validation = validate_listing_localization(
            fields,
            source_fields=source.fields,
            brand_term=brand_term,
            goal=goal,
        )
        history.append(
            {
                "provider": provider_used,
                "fields": dict(fields),
                "validation": {key: value for key, value in validation.items() if key != "history"},
            }
        )
        if not validation.get("hasErrors"):
            break
        previous_fields = fields
        raw_issues = validation.get("issues", [])
        feedback = [
            str(issue.get("message"))
            for issue in (raw_issues if isinstance(raw_issues, list) else [])
            if isinstance(issue, dict) and issue.get("message")
        ]
    final_validation = {**validation, "history": history}
    return fields, provider_used, final_validation, len(history)


def validate_listing_localization(
    fields: dict[str, str],
    *,
    source_fields: dict[str, str],
    brand_term: str,
    goal: str,
) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    for key, (minimum, maximum) in LISTING_LIMITS.items():
        value = str(fields.get(key, "")).strip()
        if minimum and len(value) < minimum:
            issues.append(
                {
                    "field": key,
                    "severity": "error",
                    "message": f"{key} is required.",
                }
            )
        if len(value) > maximum:
            issues.append(
                {
                    "field": key,
                    "severity": "error",
                    "message": f"{key} exceeds {maximum} characters.",
                }
            )
    try:
        strategy = analyze_distribution_strategy(
            str(fields.get("name", "")),
            str(fields.get("subtitle", "")),
            str(fields.get("keywords", "")),
            goal=goal if goal in {"aso_seo_aeo", "ugc_ads"} else "aso_seo_aeo",
            brand_term=brand_term,
        )
        if strategy.duplicate_words:
            issues.append(
                {
                    "field": "listing",
                    "severity": "error",
                    "message": strategy.no_repetition.detail,
                }
            )
        if strategy.title_order.passed is False:
            issues.append(
                {
                    "field": "name",
                    "severity": "error",
                    "message": strategy.title_order.detail,
                }
            )
    except ValueError as exc:
        issues.append(
            {
                "field": "listing",
                "severity": "error",
                "message": str(exc),
            }
        )
    for key in (
        "privacyPolicyUrl",
        "privacyChoicesUrl",
        "privacyPolicyText",
        "supportUrl",
        "marketingUrl",
    ):
        if source_fields.get(key) and fields.get(key) not in (None, source_fields[key]):
            issues.append(
                {
                    "field": key,
                    "severity": "error",
                    "message": f"{key} must remain unchanged.",
                }
            )
    has_errors = any(issue["severity"] == "error" for issue in issues)
    penalty = sum(20 if issue["severity"] == "error" else 5 for issue in issues)
    return {
        "hasErrors": has_errors,
        "score": max(0, 100 - penalty),
        "issues": issues,
    }


def _listing_source(
    *,
    app: App,
    main_country: str,
    metadata: ListingMetadata | None,
    settings: Settings,
) -> ListingSource:
    locale = app_store_locale_for_country(main_country)
    status = connection_status(settings)
    if status["configured"] and app.bundle_id:
        if not status["ready"]:
            raise AppStoreConnectError(
                "App Store Connect credentials are incomplete or the private key is not "
                "available with user-only permissions"
            )
        try:
            with AppStoreConnectClient(settings) as client:
                snapshot = client.snapshot(bundle_id=app.bundle_id)
            source = snapshot.localizations.get(locale)
            if source is None:
                raise AppStoreConnectError(
                    f"no App Store Connect localization exists for {locale}; choose a main "
                    "listing with an existing localization"
                )
            return ListingSource(
                country=main_country,
                locale=source.locale,
                language=APP_STORE_LOCALE_LANGUAGE.get(
                    source.locale,
                    COUNTRY_PRIMARY_LANGUAGE.get(main_country, "English"),
                ),
                fields=_localization_fields(source),
                mode="app_store_connect",
                app_info_id=source.app_info_id,
                version_id=source.version_id,
                version_state=source.version_state,
            )
        except AppStoreConnectError:
            raise
    listing = lookup_listing(
        app.apple_app_id,
        main_country,
        timeout=settings.request_timeout,
        retry_count=settings.retry_count,
    )
    return ListingSource(
        country=main_country,
        locale=locale,
        language=APP_STORE_LOCALE_LANGUAGE.get(
            locale,
            COUNTRY_PRIMARY_LANGUAGE.get(main_country, "English"),
        ),
        fields={
            "name": metadata.name if metadata is not None else listing.track_name,
            "subtitle": metadata.subtitle if metadata is not None else "",
            "keywords": metadata.keyword_field if metadata is not None else "",
            "description": listing.description,
            "promotionalText": "",
            "whatsNew": "",
            "supportUrl": "",
            "marketingUrl": "",
            "privacyPolicyUrl": "",
            "privacyChoicesUrl": "",
            "privacyPolicyText": "",
        },
        mode="local_public",
    )


def _localization_fields(
    value: AppStoreConnectLocalization,
) -> dict[str, str]:
    return {
        "name": value.name,
        "subtitle": value.subtitle,
        "keywords": value.keywords,
        "description": value.description,
        "promotionalText": value.promotional_text,
        "whatsNew": value.whats_new,
        "supportUrl": value.support_url,
        "marketingUrl": value.marketing_url,
        "privacyPolicyUrl": value.privacy_policy_url,
        "privacyChoicesUrl": value.privacy_choices_url,
        "privacyPolicyText": value.privacy_policy_text,
    }


def _localization_country(storefront: Storefront, main_country: str) -> dict[str, object]:
    locale = app_store_locale_for_country(storefront.country_code)
    return {
        "code": storefront.country_code,
        "name": storefront.display_name,
        "locale": locale,
        "language": APP_STORE_LOCALE_LANGUAGE.get(
            locale,
            COUNTRY_PRIMARY_LANGUAGE.get(storefront.country_code, "English"),
        ),
        "isMain": storefront.country_code == main_country,
    }


def _remote_localization_ids(
    *,
    app: App,
    target_locale: str,
    settings: Settings,
) -> dict[str, str | None] | None:
    status = connection_status(settings)
    if not status["ready"] or not app.bundle_id:
        return None
    with AppStoreConnectClient(settings) as client:
        snapshot = client.snapshot(bundle_id=app.bundle_id)
    source = snapshot.localizations.get(target_locale)
    return {
        "appInfoLocalizationId": (source.app_info_localization_id if source is not None else None),
        "versionLocalizationId": (source.version_localization_id if source is not None else None),
        "versionId": snapshot.version_id,
        "versionState": snapshot.version_state,
    }


def _audit_keywords_for_targets(
    session: Session,
    *,
    app_id: int,
    countries: list[str],
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for country in countries:
        run = latest_audit_run(
            session,
            app_id,
            country_code=country,
            device="iphone",
        )
        if run is None:
            continue
        for country_result in run.countries:
            if country_result.country_code != country:
                continue
            for keyword in country_result.keywords:
                normalized = keyword.normalized_keyword
                if normalized in seen:
                    continue
                seen.add(normalized)
                values.append(keyword.keyword)
    return values


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
