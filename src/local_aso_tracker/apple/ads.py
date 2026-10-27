"""Read-only client for the Apple Ads Platform API."""

from __future__ import annotations

import base64
import json
import stat
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from local_aso_tracker.config import apple_ads_credentials_path

APPLE_ADS_API_BASE = "https://api.ads.apple.com/v1"
APPLE_ADS_TOKEN_URL = "https://appleid.apple.com/auth/oauth2/token"


class AppleAdsError(RuntimeError):
    """A safe, user-facing Apple Ads API failure."""


@dataclass(frozen=True)
class AppleAdsAccountRecord:
    ad_account_id: int
    org_id: int | None
    name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class AppleAdsCampaignRecord:
    campaign_id: int
    name: str
    status: str
    promoted_object_id: int | None
    promoted_object_type: str | None
    countries: tuple[str, ...]
    deleted: bool


@dataclass(frozen=True)
class AppleAdsKeywordRecord:
    keyword_id: int
    campaign_id: int
    ad_group_id: int | None
    ad_group_name: str | None
    text: str
    match_type: str
    status: str
    display_status: str | None
    bid_amount: Decimal | None
    bid_currency: str | None
    deleted: bool


@dataclass(frozen=True)
class AppleAdsMetricRecord:
    keyword_id: int
    metric_date: date
    country_or_region: str
    device_class: str
    impressions: int
    taps: int
    local_spend: Decimal
    currency: str | None
    tap_installs: int
    total_installs: int
    ttr: Decimal | None
    cpt: Decimal | None
    suggested_bid: Decimal | None


@dataclass(frozen=True)
class AppleAdsSuggestionRecord:
    text: str
    popularity: int | None


class AppleAdsClient:
    """Authenticated read-only access to Apple Ads reporting resources."""

    def __init__(
        self,
        *,
        credentials_path: Path | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.credentials_path = credentials_path or apple_ads_credentials_path()
        self._external_client = client
        self._client = client
        self._timeout = timeout
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def credential_status(self) -> dict[str, object]:
        """Describe the local credential without returning secret material."""

        if not self.credentials_path.is_file():
            return {
                "available": False,
                "path": str(self.credentials_path),
                "reason": "Apple Ads client secret not found",
            }
        try:
            claims = _jwt_claims(self.credentials_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "available": False,
                "path": str(self.credentials_path),
                "reason": f"Invalid Apple Ads client secret: {exc}",
            }
        mode = stat.S_IMODE(self.credentials_path.stat().st_mode)
        expires_at = int(claims.get("exp", 0))
        return {
            "available": bool(claims.get("sub")) and expires_at > int(time.time()),
            "path": str(self.credentials_path),
            "private_permissions": mode & 0o077 == 0,
            "expiresAt": (
                datetime.fromtimestamp(expires_at, tz=UTC).isoformat() if expires_at else None
            ),
        }

    def accounts(self) -> list[AppleAdsAccountRecord]:
        """Return every ad account visible to the local credential."""

        payload = self._request("GET", "/acls")
        result = payload.get("result", {})
        rows = result.get("acls", []) if isinstance(result, dict) else []
        accounts: list[AppleAdsAccountRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            account = row.get("adAccount")
            if not isinstance(account, dict):
                continue
            accounts.append(
                AppleAdsAccountRecord(
                    ad_account_id=_int(account.get("id")),
                    org_id=_int_or_none(account.get("orgId")),
                    name=str(account.get("name") or f"Ad account {account.get('id')}"),
                    roles=tuple(str(role) for role in row.get("roles", [])),
                )
            )
        return accounts

    def campaigns(self, ad_account_id: int) -> list[AppleAdsCampaignRecord]:
        """Return all non-deleted and deleted campaigns in an ad account."""

        rows = self._query_pages(
            "/campaigns/query",
            {"pagination": {"offset": 0, "pageSize": 1000, "fetchTotalCount": True}},
            ad_account_id,
        )
        return [
            AppleAdsCampaignRecord(
                campaign_id=_int(row.get("id")),
                name=str(row.get("name") or f"Campaign {row.get('id')}"),
                status=str(row.get("status") or "UNKNOWN"),
                promoted_object_id=_int_or_none(row.get("promotedObjectId")),
                promoted_object_type=(
                    str(row["promotedObjectType"]) if row.get("promotedObjectType") else None
                ),
                countries=_campaign_countries(row),
                deleted=bool(row.get("deleted", False)),
            )
            for row in rows
        ]

    def keywords(
        self,
        ad_account_id: int,
        campaigns: list[AppleAdsCampaignRecord],
    ) -> list[AppleAdsKeywordRecord]:
        """Return configured targeting keywords for each campaign."""

        results: list[AppleAdsKeywordRecord] = []
        for campaign in campaigns:
            rows = self._query_pages(
                "/keywords/query",
                {
                    "filters": [
                        {
                            "field": "campaignId",
                            "operator": "EQUALS",
                            "value": campaign.campaign_id,
                        }
                    ],
                    "pagination": {"offset": 0, "pageSize": 1000, "fetchTotalCount": True},
                },
                ad_account_id,
            )
            for row in rows:
                bid = _money(row.get("bid"))
                ad_group = row.get("adGroup")
                results.append(
                    AppleAdsKeywordRecord(
                        keyword_id=_int(row.get("id")),
                        campaign_id=_int(row.get("campaignId")),
                        ad_group_id=_int_or_none(row.get("adGroupId")),
                        ad_group_name=(
                            str(ad_group["name"])
                            if isinstance(ad_group, dict) and ad_group.get("name")
                            else None
                        ),
                        text=str(row.get("text") or "").strip(),
                        match_type=str(row.get("matchType") or "UNKNOWN"),
                        status=str(row.get("status") or "UNKNOWN"),
                        display_status=(
                            str(row["displayStatus"]) if row.get("displayStatus") else None
                        ),
                        bid_amount=bid[0],
                        bid_currency=bid[1],
                        deleted=bool(row.get("deleted", False)),
                    )
                )
        return results

    def keyword_metrics(
        self,
        ad_account_id: int,
        campaigns: list[AppleAdsCampaignRecord],
        *,
        start: date,
        end: date,
    ) -> list[AppleAdsMetricRecord]:
        """Return daily country/device keyword metrics for a date window."""

        results: list[AppleAdsMetricRecord] = []
        for campaign in campaigns:
            rows = self._query_report_pages(
                "/reports/apps/keywords/query",
                {
                    "filters": [
                        {
                            "field": "campaignId",
                            "operator": "EQUALS",
                            "value": campaign.campaign_id,
                        }
                    ],
                    "groupBy": ["countryOrRegion", "deviceClass"],
                    "timeRange": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "timeZone": "ORTZ",
                        "granularity": "DAILY",
                    },
                    "pagination": {"offset": 0, "pageSize": 1000},
                },
                ad_account_id,
            )
            for row in rows:
                metadata = row.get("metadata") or {}
                insights = row.get("insights") or {}
                recommendation = insights.get("bidRecommendation") or {}
                suggested = recommendation.get("suggestedBidAmount")
                suggested_bid = _decimal_or_none(
                    suggested.get("amount") if isinstance(suggested, dict) else suggested
                )
                for metric in row.get("granularMetrics", []):
                    if not isinstance(metric, dict) or not metric.get("date"):
                        continue
                    spend, currency = _money(metric.get("localSpend"))
                    results.append(
                        AppleAdsMetricRecord(
                            keyword_id=_int(metadata.get("id")),
                            metric_date=date.fromisoformat(str(metric["date"])),
                            country_or_region=str(
                                metadata.get("countryOrRegion")
                                or metric.get("countryOrRegion")
                                or ""
                            ).upper(),
                            device_class=str(
                                metadata.get("deviceClass") or metric.get("deviceClass") or "ALL"
                            ),
                            impressions=int(metric.get("impressions") or 0),
                            taps=int(metric.get("taps") or 0),
                            local_spend=spend or Decimal("0"),
                            currency=currency,
                            tap_installs=int(metric.get("tapInstalls") or 0),
                            total_installs=int(metric.get("totalInstalls") or 0),
                            ttr=_decimal_or_none(metric.get("ttr")),
                            cpt=_money(metric.get("cpt"))[0],
                            suggested_bid=suggested_bid,
                        )
                    )
        return results

    def keyword_suggestions(
        self,
        ad_account_id: int,
        *,
        apple_app_id: int,
        country: str,
        terms: list[str],
        limit: int = 100,
    ) -> list[AppleAdsSuggestionRecord]:
        """Return Apple-ranked suggestions seeded by tracked ASO terms."""

        filters: list[dict[str, object]] = [
            {
                "field": "promotedObjectId",
                "operator": "EQUALS",
                "value": [str(apple_app_id)],
            },
            {
                "field": "promotedObjectType",
                "operator": "EQUALS",
                "value": ["APPSTORE_APP"],
            },
            {
                "field": "countriesOrRegions",
                "operator": "IN",
                "value": [country.upper()],
            },
        ]
        if terms:
            filters.append({"field": "terms", "operator": "IN", "value": terms})
        payload = self._request(
            "POST",
            "/suggestions/keywords/query",
            ad_account_id,
            json={
                "filters": filters,
                "pagination": {"offset": 0, "pageSize": min(limit, 1000)},
            },
        )
        rows = payload.get("result", [])
        if not isinstance(rows, list):
            return []
        return [
            AppleAdsSuggestionRecord(
                text=str(row.get("text") or "").strip(),
                popularity=_int_or_none(row.get("popularity")),
            )
            for row in rows
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]

    def _query_pages(
        self,
        path: str,
        body: dict[str, object],
        ad_account_id: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_body = dict(body)
            raw_pagination = page_body.get("pagination")
            pagination = dict(raw_pagination) if isinstance(raw_pagination, dict) else {}
            pagination["offset"] = offset
            page_body["pagination"] = pagination
            payload = self._request("POST", path, ad_account_id, json=page_body)
            page = payload.get("result", [])
            if not isinstance(page, list):
                raise AppleAdsError("Apple Ads returned an unexpected query result")
            rows.extend(row for row in page if isinstance(row, dict))
            offset += len(page)
            total = (payload.get("pagination") or {}).get("totalCount", offset)
            if not page or offset >= int(total):
                break
        return rows

    def _query_report_pages(
        self,
        path: str,
        body: dict[str, object],
        ad_account_id: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_body = dict(body)
            raw_pagination = page_body.get("pagination")
            pagination = dict(raw_pagination) if isinstance(raw_pagination, dict) else {}
            pagination["offset"] = offset
            page_body["pagination"] = pagination
            payload = self._request("POST", path, ad_account_id, json=page_body)
            result = payload.get("result") or {}
            page = result.get("rows", []) if isinstance(result, dict) else []
            if not isinstance(page, list):
                raise AppleAdsError("Apple Ads returned an unexpected report result")
            rows.extend(row for row in page if isinstance(row, dict))
            offset += len(page)
            total = (payload.get("pagination") or {}).get("totalCount", offset)
            if not page or offset >= int(total):
                break
        return rows

    def _request(
        self,
        method: str,
        path: str,
        ad_account_id: int | None = None,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        token = self._token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if ad_account_id is not None:
            headers["X-AP-Context"] = f"adAccountId={ad_account_id}"
        owned = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        self._client = client
        try:
            for attempt in range(3):
                try:
                    response = client.request(
                        method,
                        f"{APPLE_ADS_API_BASE}{path}",
                        headers=headers,
                        json=json,
                    )
                    if response.status_code == 401 and attempt == 0:
                        self._access_token = None
                        token = self._token()
                        headers["Authorization"] = f"Bearer {token}"
                        continue
                    if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                        time.sleep(min(2**attempt, 4))
                        continue
                    if response.is_error:
                        raise AppleAdsError(_friendly_error(response))
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise AppleAdsError("Apple Ads returned malformed JSON")
                    return payload
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt >= 2:
                        raise AppleAdsError("Apple Ads API is unavailable") from exc
                    time.sleep(min(2**attempt, 4))
        finally:
            if owned and self._client is not None:
                self._client.close()
                self._client = None
        raise AppleAdsError("Apple Ads request failed")

    def _token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        if not self.credentials_path.is_file():
            raise AppleAdsError("Apple Ads client secret not found")
        mode = stat.S_IMODE(self.credentials_path.stat().st_mode)
        if mode & 0o077:
            raise AppleAdsError("Apple Ads client secret must use owner-only permissions")
        secret = self.credentials_path.read_text(encoding="utf-8").strip()
        claims = _jwt_claims(secret)
        client_id = str(claims.get("sub") or "")
        expires_at = int(claims.get("exp", 0))
        if not client_id:
            raise AppleAdsError("Apple Ads client secret does not contain a client ID")
        if expires_at <= int(time.time()):
            raise AppleAdsError("Apple Ads client secret has expired")
        client = self._client or httpx.Client(timeout=self._timeout)
        owned = self._client is None
        if owned:
            self._client = client
        try:
            response = client.post(
                APPLE_ADS_TOKEN_URL,
                headers={"Host": "appleid.apple.com"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": secret,
                    "scope": "searchadsorg",
                },
            )
            if response.is_error:
                raise AppleAdsError(_friendly_error(response))
            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise AppleAdsError("Apple Ads token response did not include an access token")
            self._access_token = token
            self._token_expires_at = time.monotonic() + max(
                60, int(payload.get("expires_in", 3600)) - 60
            )
            return token
        finally:
            if owned:
                client.close()
                self._client = None


def _jwt_claims(secret: str) -> dict[str, Any]:
    parts = secret.split(".")
    if len(parts) != 3:
        raise ValueError("expected a signed JWT")
    encoded = parts[1] + "=" * (-len(parts[1]) % 4)
    value = json.loads(base64.urlsafe_b64decode(encoded))
    if not isinstance(value, dict):
        raise ValueError("JWT payload must be an object")
    return value


def _friendly_error(response: httpx.Response) -> str:
    try:
        raw = response.json()
        error = raw.get("error", {})
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
        else:
            message = str(error)
    except (ValueError, TypeError):
        message = None
    return f"Apple Ads API returned HTTP {response.status_code}: {message or 'request failed'}"


def _money(value: object) -> tuple[Decimal | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    return _decimal_or_none(value.get("amount")), (
        str(value["currency"]) if value.get("currency") else None
    )


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def _int(value: object) -> int:
    return int(str(value))


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def _campaign_countries(row: dict[str, Any]) -> tuple[str, ...]:
    targeting = row.get("targeting")
    if not isinstance(targeting, dict):
        return ()
    countries = targeting.get("countryOrRegion")
    if not isinstance(countries, dict):
        return ()
    includes = countries.get("include")
    if not isinstance(includes, list):
        return ()
    return tuple(
        str(country).upper() for country in includes if isinstance(country, str) and country
    )
