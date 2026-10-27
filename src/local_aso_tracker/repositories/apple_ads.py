"""Persistence for read-only Apple Ads reporting data."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.apple.ads import (
    AppleAdsAccountRecord,
    AppleAdsCampaignRecord,
    AppleAdsKeywordRecord,
    AppleAdsMetricRecord,
    AppleAdsSuggestionRecord,
)
from local_aso_tracker.models import (
    App,
    AppleAdsAccount,
    AppleAdsCampaign,
    AppleAdsKeyword,
    AppleAdsKeywordMetric,
    AppleAdsSuggestion,
    Storefront,
)
from local_aso_tracker.repositories.data import latest_pairs, list_targets, normalize_keyword


def upsert_account(session: Session, record: AppleAdsAccountRecord) -> AppleAdsAccount:
    item = session.scalar(
        select(AppleAdsAccount).where(AppleAdsAccount.ad_account_id == record.ad_account_id)
    )
    if item is None:
        item = AppleAdsAccount(
            ad_account_id=record.ad_account_id,
            org_id=record.org_id,
            name=record.name,
            roles=", ".join(record.roles),
        )
        session.add(item)
    else:
        item.org_id = record.org_id
        item.name = record.name
        item.roles = ", ".join(record.roles)
    session.flush()
    return item


def replace_campaigns(
    session: Session,
    account: AppleAdsAccount,
    records: list[AppleAdsCampaignRecord],
) -> dict[int, AppleAdsCampaign]:
    existing = {
        item.campaign_id: item
        for item in session.scalars(
            select(AppleAdsCampaign).where(AppleAdsCampaign.ad_account_id == account.id)
        )
    }
    now = datetime.now(UTC)
    result: dict[int, AppleAdsCampaign] = {}
    active_ids: set[int] = set()
    for record in records:
        active_ids.add(record.campaign_id)
        item = existing.get(record.campaign_id)
        if item is None:
            item = AppleAdsCampaign(
                ad_account_id=account.id,
                campaign_id=record.campaign_id,
                name=record.name,
                status=record.status,
                promoted_object_id=record.promoted_object_id,
                promoted_object_type=record.promoted_object_type,
                countries=",".join(record.countries),
                deleted=record.deleted,
                synced_at=now,
            )
            session.add(item)
        else:
            item.name = record.name
            item.status = record.status
            item.promoted_object_id = record.promoted_object_id
            item.promoted_object_type = record.promoted_object_type
            item.countries = ",".join(record.countries)
            item.deleted = record.deleted
            item.synced_at = now
        result[record.campaign_id] = item
    for campaign_id, item in existing.items():
        if campaign_id not in active_ids:
            item.deleted = True
            item.synced_at = now
    session.flush()
    return result


def replace_keywords(
    session: Session,
    campaigns: dict[int, AppleAdsCampaign],
    records: list[AppleAdsKeywordRecord],
) -> dict[int, AppleAdsKeyword]:
    campaign_database_ids = {item.id for item in campaigns.values()}
    existing = {
        (item.campaign_id, item.keyword_id): item
        for item in session.scalars(
            select(AppleAdsKeyword).where(AppleAdsKeyword.campaign_id.in_(campaign_database_ids))
        )
    }
    now = datetime.now(UTC)
    result: dict[int, AppleAdsKeyword] = {}
    seen: set[tuple[int, int]] = set()
    for record in records:
        campaign = campaigns.get(record.campaign_id)
        if campaign is None:
            continue
        key = (campaign.id, record.keyword_id)
        seen.add(key)
        item = existing.get(key)
        if item is None:
            item = AppleAdsKeyword(
                campaign_id=campaign.id,
                keyword_id=record.keyword_id,
                ad_group_id=record.ad_group_id,
                ad_group_name=record.ad_group_name,
                text=record.text,
                normalized_text=normalize_keyword(record.text),
                match_type=record.match_type,
                status=record.status,
                display_status=record.display_status,
                bid_amount=record.bid_amount,
                bid_currency=record.bid_currency,
                deleted=record.deleted,
                synced_at=now,
            )
            session.add(item)
        else:
            item.ad_group_id = record.ad_group_id
            item.ad_group_name = record.ad_group_name
            item.text = record.text
            item.normalized_text = normalize_keyword(record.text)
            item.match_type = record.match_type
            item.status = record.status
            item.display_status = record.display_status
            item.bid_amount = record.bid_amount
            item.bid_currency = record.bid_currency
            item.deleted = record.deleted
            item.synced_at = now
        result[record.keyword_id] = item
    for key, item in existing.items():
        if key not in seen:
            item.deleted = True
            item.synced_at = now
    session.flush()
    return result


def replace_metrics(
    session: Session,
    account: AppleAdsAccount,
    keywords: dict[int, AppleAdsKeyword],
    records: list[AppleAdsMetricRecord],
    *,
    start: date,
    end: date,
) -> int:
    session.execute(
        delete(AppleAdsKeywordMetric).where(
            AppleAdsKeywordMetric.ad_account_id == account.id,
            AppleAdsKeywordMetric.metric_date >= start,
            AppleAdsKeywordMetric.metric_date <= end,
        )
    )
    now = datetime.now(UTC)
    count = 0
    for record in records:
        keyword = keywords.get(record.keyword_id)
        if keyword is None:
            continue
        session.add(
            AppleAdsKeywordMetric(
                ad_account_id=account.id,
                apple_ads_keyword_id=keyword.id,
                metric_date=record.metric_date,
                country_or_region=record.country_or_region,
                device_class=record.device_class,
                impressions=record.impressions,
                taps=record.taps,
                local_spend=record.local_spend,
                currency=record.currency,
                tap_installs=record.tap_installs,
                total_installs=record.total_installs,
                ttr=record.ttr,
                cpt=record.cpt,
                suggested_bid=record.suggested_bid,
                synced_at=now,
            )
        )
        count += 1
    session.flush()
    return count


def replace_suggestions(
    session: Session,
    app: App,
    country: str,
    records: list[AppleAdsSuggestionRecord],
) -> None:
    session.execute(
        delete(AppleAdsSuggestion).where(
            AppleAdsSuggestion.app_id == app.id,
            AppleAdsSuggestion.country_or_region == country.upper(),
        )
    )
    now = datetime.now(UTC)
    seen: set[str] = set()
    for record in records:
        normalized = normalize_keyword(record.text)
        if normalized in seen:
            continue
        seen.add(normalized)
        session.add(
            AppleAdsSuggestion(
                app_id=app.id,
                country_or_region=country.upper(),
                text=record.text,
                normalized_text=normalized,
                popularity=record.popularity,
                fetched_at=now,
            )
        )


def touch_account(session: Session, account: AppleAdsAccount) -> None:
    account.last_synced_at = datetime.now(UTC)


def apple_ads_payload(
    session: Session,
    *,
    apple_app_id: int | None,
    country: str,
    device: str,
    selected_account_id: int,
    days: int,
    start: date,
    end: date,
) -> dict[str, object]:
    accounts = list(
        session.scalars(
            select(AppleAdsAccount).order_by(AppleAdsAccount.name, AppleAdsAccount.ad_account_id)
        )
    )
    selected = next(
        (item for item in accounts if item.ad_account_id == selected_account_id),
        None,
    )
    payload: dict[str, object] = {
        "accounts": [
            {
                "id": item.ad_account_id,
                "orgId": item.org_id,
                "name": item.name,
                "roles": [role.strip() for role in item.roles.split(",") if role.strip()],
                "lastSyncedAt": _iso(item.last_synced_at),
            }
            for item in accounts
        ],
        "selectedAccountId": selected.ad_account_id if selected else None,
        "window": {"days": days, "start": start.isoformat(), "end": end.isoformat()},
        "campaigns": [],
        "keywords": [],
        "keywordCountries": [],
        "suggestions": [],
        "summary": _metric_summary([]),
        "allMarketsSummary": _metric_summary([]),
    }
    if apple_app_id is None or selected is None:
        return payload

    app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
    if app is None:
        return payload
    campaigns = list(
        session.scalars(
            select(AppleAdsCampaign)
            .where(
                AppleAdsCampaign.ad_account_id == selected.id,
                AppleAdsCampaign.promoted_object_id == apple_app_id,
                AppleAdsCampaign.deleted.is_(False),
            )
            .options(selectinload(AppleAdsCampaign.keywords))
            .order_by(AppleAdsCampaign.name)
        )
    )
    keyword_rows = [
        keyword for campaign in campaigns for keyword in campaign.keywords if not keyword.deleted
    ]
    keyword_db_ids = [item.id for item in keyword_rows]
    device_class = "iPad" if device == "ipad" else "iPhone"
    metric_rows = (
        list(
            session.scalars(
                select(AppleAdsKeywordMetric).where(
                    AppleAdsKeywordMetric.ad_account_id == selected.id,
                    AppleAdsKeywordMetric.apple_ads_keyword_id.in_(keyword_db_ids),
                    AppleAdsKeywordMetric.metric_date >= start,
                    AppleAdsKeywordMetric.metric_date <= end,
                    AppleAdsKeywordMetric.country_or_region == country.upper(),
                    AppleAdsKeywordMetric.device_class == device_class,
                )
            )
        )
        if keyword_db_ids
        else []
    )
    all_metric_rows = (
        list(
            session.scalars(
                select(AppleAdsKeywordMetric).where(
                    AppleAdsKeywordMetric.ad_account_id == selected.id,
                    AppleAdsKeywordMetric.apple_ads_keyword_id.in_(keyword_db_ids),
                    AppleAdsKeywordMetric.metric_date >= start,
                    AppleAdsKeywordMetric.metric_date <= end,
                )
            )
        )
        if keyword_db_ids
        else []
    )
    device_metric_rows = (
        list(
            session.scalars(
                select(AppleAdsKeywordMetric).where(
                    AppleAdsKeywordMetric.ad_account_id == selected.id,
                    AppleAdsKeywordMetric.apple_ads_keyword_id.in_(keyword_db_ids),
                    AppleAdsKeywordMetric.metric_date >= start,
                    AppleAdsKeywordMetric.metric_date <= end,
                    AppleAdsKeywordMetric.device_class == device_class,
                )
            )
        )
        if keyword_db_ids
        else []
    )
    metrics_by_keyword: dict[int, list[AppleAdsKeywordMetric]] = defaultdict(list)
    for metric in metric_rows:
        metrics_by_keyword[metric.apple_ads_keyword_id].append(metric)
    country_metrics_by_keyword: dict[tuple[int, str], list[AppleAdsKeywordMetric]] = defaultdict(
        list
    )
    for metric in device_metric_rows:
        country_metrics_by_keyword[
            (metric.apple_ads_keyword_id, metric.country_or_region.upper())
        ].append(metric)

    targets = list_targets(
        session,
        apple_id=apple_app_id,
        device=device,
        active_only=True,
    )
    track_by_keyword = {
        target.keyword.normalized_keyword: target
        for target in targets
        if target.storefront.country_code == country
    }
    pairs = latest_pairs(session, targets)
    aso_rows = {
        (target.storefront.country_code.upper(), target.keyword.normalized_keyword): pair[0]
        for target in targets
        if (pair := pairs.get(target.id)) is not None
    }
    campaign_payload: dict[int, dict[str, object]] = {}
    for campaign in campaigns:
        campaign_payload[campaign.id] = {
            "id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status,
            "deleted": campaign.deleted,
            "keywordCount": sum(not item.deleted for item in campaign.keywords),
            "enabledKeywordCount": sum(
                not item.deleted and item.status == "ENABLED" for item in campaign.keywords
            ),
            "summary": _metric_summary(
                [
                    metric
                    for keyword in campaign.keywords
                    for metric in metrics_by_keyword.get(keyword.id, [])
                ]
            ),
        }

    country_keyword_records: dict[str, dict[str, list[AppleAdsKeyword]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for keyword in keyword_rows:
        for country_code in keyword.campaign.countries.split(","):
            if country_code:
                country_keyword_records[country_code][keyword.normalized_text].append(keyword)
    country_names = {
        item.country_code.upper(): item.display_name for item in session.scalars(select(Storefront))
    }
    keyword_countries: list[dict[str, object]] = []
    all_country_keyword_rows: list[dict[str, object]] = []
    for country_code, grouped_keywords in country_keyword_records.items():
        country_keyword_rows: list[dict[str, object]] = []
        country_metric_rows: list[AppleAdsKeywordMetric] = []
        for normalized_text, keywords in grouped_keywords.items():
            metrics = [
                metric
                for keyword in keywords
                for metric in country_metrics_by_keyword.get((keyword.id, country_code), [])
            ]
            country_metric_rows.extend(metrics)
            bids = [item.bid_amount for item in keywords if item.bid_amount is not None]
            currencies = sorted(
                {item.bid_currency for item in keywords if item.bid_currency is not None}
            )
            aso_check = aso_rows.get((country_code, normalized_text))
            aso_checked = bool(aso_check and aso_check.status == "success")
            row = {
                "country": country_code,
                "countryName": country_names.get(country_code, country_code),
                "text": keywords[0].text,
                "matchTypes": sorted({item.match_type for item in keywords}),
                "status": (
                    "ENABLED"
                    if any(
                        item.status == "ENABLED" and item.campaign.status == "ENABLED"
                        for item in keywords
                    )
                    else "PAUSED"
                ),
                "campaignStatus": (
                    "ENABLED"
                    if any(item.campaign.status == "ENABLED" for item in keywords)
                    else "PAUSED"
                ),
                "campaignCount": len({item.campaign.campaign_id for item in keywords}),
                "campaigns": sorted({item.campaign.name for item in keywords}),
                "bidMin": _decimal_string(min(bids)) if bids else None,
                "bidMax": _decimal_string(max(bids)) if bids else None,
                "currency": currencies[0] if len(currencies) == 1 else None,
                "metrics": _metric_summary(metrics),
                "asoRank": aso_check.rank if aso_check and aso_check.found else None,
                "asoFound": bool(aso_check and aso_check.found),
                "asoChecked": aso_checked,
                "asoLimit": aso_check.result_limit if aso_checked and aso_check else None,
                "asoError": bool(aso_check and aso_check.status == "error"),
            }
            country_keyword_rows.append(row)
            all_country_keyword_rows.append(row)
        country_keyword_rows.sort(
            key=lambda item: (
                str(item["status"]) != "ENABLED",
                str(item["text"]).casefold(),
            )
        )
        keyword_countries.append(
            {
                "code": country_code,
                "name": country_names.get(country_code, country_code),
                "summary": _metric_summary(country_metric_rows),
                "keywords": country_keyword_rows,
            }
        )

    def country_sort_key(
        item: dict[str, object],
    ) -> tuple[bool, Decimal, str]:
        summary = item.get("summary")
        spend = summary.get("spend", "0") if isinstance(summary, dict) else "0"
        return (
            item.get("code") != country.upper(),
            -Decimal(str(spend)),
            str(item.get("name", "")).casefold(),
        )

    keyword_countries.sort(key=country_sort_key)

    tracked_terms = {
        str(row["text"]).casefold()
        for row in all_country_keyword_rows
        if row["country"] == country.upper()
    }
    suggestions = list(
        session.scalars(
            select(AppleAdsSuggestion)
            .where(
                AppleAdsSuggestion.app_id == app.id,
                AppleAdsSuggestion.country_or_region == country.upper(),
            )
            .order_by(
                AppleAdsSuggestion.popularity.desc().nullslast(),
                AppleAdsSuggestion.text,
            )
        )
    )
    suggestion_payload = [
        {
            "text": item.text,
            "popularity": item.popularity,
            "inAppleAds": item.normalized_text in tracked_terms,
            "inAsoTracker": item.normalized_text in track_by_keyword,
            "fetchedAt": _iso(item.fetched_at),
        }
        for item in suggestions
    ]
    payload["campaigns"] = sorted(
        campaign_payload.values(),
        key=lambda item: (str(item["status"]) != "ENABLED", str(item["name"]).casefold()),
    )
    payload["keywords"] = sorted(
        all_country_keyword_rows,
        key=lambda item: (
            str(item["country"]) != country.upper(),
            str(item["status"]) != "ENABLED",
            str(item["text"]).casefold(),
        ),
    )
    payload["keywordCountries"] = keyword_countries
    payload["suggestions"] = suggestion_payload
    payload["summary"] = _metric_summary(metric_rows)
    payload["allMarketsSummary"] = _metric_summary(all_metric_rows)
    payload["suggestionsFetchedAt"] = (
        suggestion_payload[0]["fetchedAt"] if suggestion_payload else None
    )
    return payload


def tracked_suggestion_terms(
    session: Session,
    *,
    apple_app_id: int,
    country: str,
    device: str,
    limit: int = 4,
) -> list[str]:
    targets = list_targets(
        session,
        apple_id=apple_app_id,
        country=country,
        device=device,
        active_only=True,
    )
    pairs = latest_pairs(session, targets)
    ranked: list[tuple[int, str]] = []
    app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
    brand_tokens = set(app.name.casefold().split()) if app is not None else set()
    for target in targets:
        pair = pairs.get(target.id)
        rank = pair[0].rank if pair and pair[0].found and pair[0].rank is not None else 10**9
        ranked.append((rank, target.keyword.keyword))
    ranked.sort(key=lambda item: (item[0], item[1].casefold()))
    keywords = [
        (normalize_keyword(keyword).replace("'", " ").replace("\u2019", " "))
        for _, keyword in ranked
    ]
    stopwords = {
        "app",
        "apps",
        "basic",
        "basics",
        "beginner",
        "beginners",
        "best",
        "class",
        "classes",
        "course",
        "courses",
        "free",
        "guide",
        "guides",
        "learn",
        "learning",
        "lesson",
        "lessons",
        "quiz",
        "school",
        "study",
        "tutorial",
    }
    token_counts: dict[str, int] = defaultdict(int)
    for keyword in keywords:
        for token in set(keyword.split()):
            if len(token) >= 4 and token not in stopwords and token not in brand_tokens:
                token_counts[token] += 1
    single_seed = (
        sorted(token_counts, key=lambda token: (-token_counts[token], token))[0]
        if token_counts
        else None
    )
    bigram_counts: dict[str, int] = defaultdict(int)
    for keyword in keywords:
        tokens = keyword.split()
        for index in range(len(tokens) - 1):
            first, second = tokens[index : index + 2]
            if first in stopwords or second in stopwords:
                continue
            if first in brand_tokens or second in brand_tokens:
                continue
            bigram_counts[f"{first} {second}"] += 1
    bigrams = sorted(bigram_counts, key=lambda phrase: (-bigram_counts[phrase], phrase))
    seeds = ([single_seed] if single_seed else []) + bigrams
    return list(dict.fromkeys(seeds))[:limit]


def _metric_summary(rows: list[AppleAdsKeywordMetric]) -> dict[str, object]:
    spend = sum((row.local_spend for row in rows), Decimal("0"))
    impressions = sum(row.impressions for row in rows)
    taps = sum(row.taps for row in rows)
    tap_installs = sum(row.tap_installs for row in rows)
    total_installs = sum(row.total_installs for row in rows)
    currencies = sorted({row.currency for row in rows if row.currency})
    return {
        "spend": _decimal_string(spend),
        "currency": currencies[0] if len(currencies) == 1 else None,
        "impressions": impressions,
        "taps": taps,
        "tapInstalls": tap_installs,
        "totalInstalls": total_installs,
        "cpt": _decimal_string(spend / taps) if taps else None,
    }


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
