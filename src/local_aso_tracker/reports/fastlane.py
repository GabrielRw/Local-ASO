"""Export localized App Store listings as a fastlane `deliver` metadata folder.

Layout: ``<output>/metadata/<locale>/<field>.txt``, using App Store Connect locale codes
(the same names fastlane uses). Only non-empty fields are written, so `deliver` leaves
anything Local ASO doesn't know about untouched. Nothing is uploaded from here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_aso_tracker.models import App, ListingMetadata, Storefront
from local_aso_tracker.repositories.listing_localizations import (
    get_main_localization_country,
    list_localization_drafts,
)
from local_aso_tracker.services.listing_localization import LISTING_LIMITS
from local_aso_tracker.services.localization_targets import app_store_locale_for_country

# Local ASO field -> fastlane file name.
LISTING_FILES = {
    "name": "name.txt",
    "subtitle": "subtitle.txt",
    "keywords": "keywords.txt",
    "description": "description.txt",
    "promotionalText": "promotional_text.txt",
    "whatsNew": "release_notes.txt",
}
URL_FILES = {
    "supportUrl": "support_url.txt",
    "marketingUrl": "marketing_url.txt",
    "privacyPolicyUrl": "privacy_url.txt",
}
EXPORTABLE_STATUSES = {"approved", "pushed"}


@dataclass(frozen=True)
class FastlaneExport:
    metadata_dir: Path
    locales: list[str]
    skipped: list[dict[str, str]]


def _json(value: str | None) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _check_limits(locale: str, fields: dict[str, str]) -> None:
    for key, (_minimum, maximum) in LISTING_LIMITS.items():
        value = fields.get(key, "")
        if len(value) > maximum:
            raise ValueError(
                f"{locale} {key} is {len(value)} characters; App Store Connect allows {maximum}"
            )


def _write_locale(folder: Path, fields: dict[str, str], urls: dict[str, str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for key, filename in LISTING_FILES.items():
        value = fields.get(key, "").strip()
        if value:
            (folder / filename).write_text(value + "\n", encoding="utf-8")
    for key, filename in URL_FILES.items():
        value = urls.get(key, "").strip()
        if value:
            (folder / filename).write_text(value + "\n", encoding="utf-8")


def export_fastlane_metadata(
    session: Session, app: App, output: Path, *, include_unapproved: bool = False
) -> FastlaneExport:
    """Write the main listing plus every approved (or every) localized draft."""

    drafts = list_localization_drafts(session, app_id=app.id)
    main_country = get_main_localization_country(session, app.id)
    metadata_dir = output / "metadata"
    written: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    skipped: list[dict[str, str]] = []

    # Main listing: the source copy captured with the drafts, else the saved metadata.
    source: dict[str, object] = _json(drafts[0].source_fields) if drafts else {}
    main_locale = drafts[0].source_locale if drafts else None
    if not source:
        # The listing saved in Optimize: the studio's main storefront, else the US, else any.
        saved_rows = {
            country: row
            for row, country in session.execute(
                select(ListingMetadata, Storefront.country_code)
                .join(Storefront, ListingMetadata.storefront_id == Storefront.id)
                .where(ListingMetadata.app_id == app.id)
                .order_by(Storefront.country_code)
            )
        }
        chosen = next(
            (
                country
                for country in (main_country, "us", *saved_rows)
                if country and country in saved_rows
            ),
            None,
        )
        if chosen is not None:
            saved = saved_rows[chosen]
            source = {
                "name": saved.name,
                "subtitle": saved.subtitle,
                "keywords": saved.keyword_field,
            }
            main_locale = app_store_locale_for_country(chosen)
    source_urls = {key: str(source.get(key, "")) for key in URL_FILES}
    if source and main_locale:
        fields = {key: str(source.get(key, "")) for key in LISTING_FILES}
        _check_limits(main_locale, fields)
        written[main_locale] = (fields, source_urls)

    for draft in drafts:
        if draft.status not in EXPORTABLE_STATUSES and not include_unapproved:
            skipped.append({"locale": draft.target_locale, "reason": f"status is {draft.status}"})
            continue
        fields = {key: str(_json(draft.fields).get(key, "")) for key in LISTING_FILES}
        _check_limits(draft.target_locale, fields)
        written[draft.target_locale] = (fields, source_urls)

    if not written:
        raise ValueError(
            "Nothing to export yet: save the listing in Optimize or approve a localized draft"
        )
    for locale, (fields, urls) in written.items():
        _write_locale(metadata_dir / locale, fields, urls)
    return FastlaneExport(metadata_dir=metadata_dir, locales=sorted(written), skipped=skipped)
