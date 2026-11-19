"""Persistence for localized App Store listing drafts and push history."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.models import (
    ListingLocalizationDraft,
    ListingLocalizationIteration,
    ListingLocalizationSettings,
    ListingPushEvent,
)


def get_localization_draft(
    session: Session,
    *,
    app_id: int,
    target_locale: str,
) -> ListingLocalizationDraft | None:
    return session.scalar(
        _draft_query().where(
            ListingLocalizationDraft.app_id == app_id,
            ListingLocalizationDraft.target_locale == target_locale,
        )
    )


def list_localization_drafts(
    session: Session,
    *,
    app_id: int,
) -> list[ListingLocalizationDraft]:
    return list(
        session.scalars(
            _draft_query()
            .where(ListingLocalizationDraft.app_id == app_id)
            .order_by(ListingLocalizationDraft.updated_at.desc())
        )
    )


def get_main_localization_country(
    session: Session,
    app_id: int,
) -> str | None:
    settings = session.get(ListingLocalizationSettings, app_id)
    return settings.main_country if settings is not None else None


def save_main_localization_country(
    session: Session,
    *,
    app_id: int,
    country: str,
) -> ListingLocalizationSettings:
    settings = session.get(ListingLocalizationSettings, app_id)
    if settings is None:
        settings = ListingLocalizationSettings(app_id=app_id, main_country=country)
        session.add(settings)
    else:
        settings.main_country = country
        settings.updated_at = datetime.now(UTC)
    session.flush()
    return settings


def upsert_localization_draft(
    session: Session,
    *,
    app_id: int,
    source_country: str,
    source_locale: str,
    target_locale: str,
    target_countries: list[str],
    language: str,
    provider: str,
    source_fields: dict[str, str],
    fields: dict[str, str],
    validation: dict[str, object],
    iteration_count: int,
    remote_ids: dict[str, str | None] | None = None,
) -> ListingLocalizationDraft:
    draft = get_localization_draft(
        session,
        app_id=app_id,
        target_locale=target_locale,
    )
    if draft is None:
        draft = ListingLocalizationDraft(
            app_id=app_id,
            source_country=source_country,
            source_locale=source_locale,
            target_locale=target_locale,
            target_countries="[]",
            language=language,
            status="needs_review",
        )
        session.add(draft)
    draft.source_country = source_country
    draft.source_locale = source_locale
    draft.target_countries = json.dumps(target_countries, ensure_ascii=False)
    draft.language = language
    draft.status = "needs_review"
    draft.iteration_count = iteration_count
    draft.provider = provider
    draft.source_fields = json.dumps(source_fields, ensure_ascii=False)
    draft.fields = json.dumps(fields, ensure_ascii=False)
    draft.validation = json.dumps(validation, ensure_ascii=False)
    draft.error_message = None
    draft.approved_at = None
    draft.pushed_at = None
    for iteration in list(draft.iterations):
        session.delete(iteration)
    session.flush()
    if remote_ids:
        draft.remote_app_info_localization_id = remote_ids.get("appInfoLocalizationId")
        draft.remote_version_localization_id = remote_ids.get("versionLocalizationId")
        draft.remote_version_id = remote_ids.get("versionId")
        draft.remote_version_state = remote_ids.get("versionState")
    draft.updated_at = datetime.now(UTC)
    session.flush()
    return draft


def add_localization_iteration(
    session: Session,
    *,
    draft: ListingLocalizationDraft,
    iteration: int,
    provider: str,
    fields: dict[str, str],
    validation: dict[str, object],
) -> ListingLocalizationIteration:
    item = ListingLocalizationIteration(
        draft_id=draft.id,
        iteration=iteration,
        provider=provider,
        fields=json.dumps(fields, ensure_ascii=False),
        validation=json.dumps(validation, ensure_ascii=False),
    )
    session.add(item)
    session.flush()
    return item


def approve_localization_draft(
    session: Session,
    draft: ListingLocalizationDraft,
) -> None:
    validation = _json_object(draft.validation)
    if validation.get("hasErrors"):
        raise ValueError("resolve validation errors before approving this localization")
    draft.status = "approved"
    draft.approved_at = datetime.now(UTC)
    draft.updated_at = datetime.now(UTC)


def record_push_event(
    session: Session,
    *,
    draft: ListingLocalizationDraft,
    status: str,
    fields: dict[str, object],
    before_values: dict[str, object],
    after_values: dict[str, object],
    error: str | None = None,
) -> ListingPushEvent:
    event = ListingPushEvent(
        draft_id=draft.id,
        status=status,
        fields=json.dumps(fields, ensure_ascii=False),
        before_values=json.dumps(before_values, ensure_ascii=False),
        after_values=json.dumps(after_values, ensure_ascii=False),
        error_message=error,
    )
    session.add(event)
    if status == "success":
        draft.status = "pushed"
        draft.pushed_at = datetime.now(UTC)
    else:
        draft.status = "failed"
        draft.error_message = error
    draft.updated_at = datetime.now(UTC)
    session.flush()
    return event


def localization_drafts_payload(
    session: Session,
    *,
    app_id: int,
) -> list[dict[str, object]]:
    return [_draft_payload(item) for item in list_localization_drafts(session, app_id=app_id)]


def draft_public_payload(draft: ListingLocalizationDraft) -> dict[str, object]:
    return _draft_payload(draft)


def _draft_payload(draft: ListingLocalizationDraft) -> dict[str, object]:
    return {
        "id": draft.id,
        "appId": draft.app_id,
        "sourceCountry": draft.source_country,
        "sourceLocale": draft.source_locale,
        "targetLocale": draft.target_locale,
        "targetCountries": _json_list(draft.target_countries),
        "language": draft.language,
        "status": draft.status,
        "iterationCount": draft.iteration_count,
        "provider": draft.provider,
        "sourceFields": _json_object(draft.source_fields),
        "fields": _json_object(draft.fields),
        "validation": _json_object(draft.validation),
        "remote": {
            "appInfoLocalizationId": draft.remote_app_info_localization_id,
            "versionLocalizationId": draft.remote_version_localization_id,
            "versionId": draft.remote_version_id,
            "versionState": draft.remote_version_state,
        },
        "error": draft.error_message,
        "createdAt": _iso(draft.created_at),
        "updatedAt": _iso(draft.updated_at),
        "approvedAt": _iso(draft.approved_at),
        "pushedAt": _iso(draft.pushed_at),
        "iterations": [
            {
                "iteration": item.iteration,
                "provider": item.provider,
                "fields": _json_object(item.fields),
                "validation": _json_object(item.validation),
                "createdAt": _iso(item.created_at),
            }
            for item in sorted(draft.iterations, key=lambda value: value.iteration)
        ],
        "pushEvents": [
            {
                "status": item.status,
                "fields": _json_object(item.fields),
                "beforeValues": _json_object(item.before_values),
                "afterValues": _json_object(item.after_values),
                "error": item.error_message,
                "createdAt": _iso(item.created_at),
            }
            for item in sorted(draft.push_events, key=lambda value: value.created_at)
        ],
    }


def _draft_query() -> Select[tuple[ListingLocalizationDraft]]:
    return select(ListingLocalizationDraft).options(
        selectinload(ListingLocalizationDraft.iterations),
        selectinload(ListingLocalizationDraft.push_events),
    )


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[str]:
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
