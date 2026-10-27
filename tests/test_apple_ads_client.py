"""Apple Ads Platform API client tests using mocked HTTP."""

import base64
import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

from local_aso_tracker.apple.ads import AppleAdsClient


def test_apple_ads_client_parses_accounts_campaigns_keywords_and_metrics(
    tmp_path: Path,
) -> None:
    secret_path = _write_secret(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "appleid.apple.com":
            return httpx.Response(
                200,
                json={"access_token": "test-token", "expires_in": 3600},
                request=request,
            )
        assert request.headers["authorization"] == "Bearer test-token"
        if request.url.path.endswith("/acls"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "acls": [
                            {
                                "adAccount": {
                                    "id": 22024640,
                                    "orgId": 42,
                                    "name": "Example",
                                },
                                "roles": ["API Campaign Manager"],
                            }
                        ]
                    }
                },
                request=request,
            )
        if request.url.path.endswith("/campaigns/query"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": 11,
                            "name": "US Exact",
                            "status": "ENABLED",
                            "promotedObjectId": "6771773264",
                            "promotedObjectType": "APPSTORE_APP",
                            "targeting": {"countryOrRegion": {"include": ["US"]}},
                            "deleted": False,
                        }
                    ],
                    "pagination": {"totalCount": 1},
                },
                request=request,
            )
        if request.url.path.endswith("/reports/apps/keywords/query"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "rows": [
                            {
                                "metadata": {
                                    "id": 21,
                                    "countryOrRegion": "US",
                                    "deviceClass": "iPhone",
                                },
                                "insights": {"bidRecommendation": {"suggestedBidAmount": 1.2}},
                                "granularMetrics": [
                                    {
                                        "date": "2026-10-01",
                                        "impressions": 100,
                                        "taps": 4,
                                        "localSpend": {
                                            "amount": "1.60",
                                            "currency": "EUR",
                                        },
                                        "tapInstalls": 2,
                                        "totalInstalls": 3,
                                        "ttr": 0.04,
                                        "cpt": {
                                            "amount": "0.40",
                                            "currency": "EUR",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    "pagination": {"totalCount": 1},
                },
                request=request,
            )
        if request.url.path.endswith("/suggestions/keywords/query"):
            return httpx.Response(
                200,
                json={
                    "result": [{"text": "astrology birth chart", "popularity": 14}],
                    "pagination": {"totalCount": 1},
                },
                request=request,
            )
        if request.url.path.endswith("/keywords/query"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": 21,
                            "campaignId": 11,
                            "adGroupId": 31,
                            "adGroup": {"name": "Core"},
                            "text": "birth chart",
                            "matchType": "EXACT",
                            "status": "ENABLED",
                            "displayStatus": "RUNNING",
                            "bid": {"amount": "0.80", "currency": "EUR"},
                            "deleted": False,
                        }
                    ],
                    "pagination": {"totalCount": 1},
                },
                request=request,
            )
        raise AssertionError(f"unexpected Apple Ads URL: {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = AppleAdsClient(credentials_path=secret_path, client=http)

    assert client.credential_status()["available"] is True
    accounts = client.accounts()
    campaigns = client.campaigns(22024640)
    keywords = client.keywords(22024640, campaigns)
    metrics = client.keyword_metrics(
        22024640,
        campaigns,
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
    )
    suggestions = client.keyword_suggestions(
        22024640,
        apple_app_id=6771773264,
        country="us",
        terms=["birth chart"],
    )
    http.close()

    assert accounts[0].name == "Example"
    assert campaigns[0].promoted_object_id == 6771773264
    assert campaigns[0].countries == ("US",)
    assert keywords[0].bid_amount == Decimal("0.80")
    assert metrics[0].local_spend == Decimal("1.60")
    assert metrics[0].country_or_region == "US"
    assert suggestions[0].popularity == 14


def _write_secret(tmp_path: Path) -> Path:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "SEARCHADS.TEST",
                    "exp": int(time.time()) + 3600,
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    path = tmp_path / "client-secret.jwt"
    path.write_text(f"e30.{payload}.signature", encoding="utf-8")
    path.chmod(0o600)
    return path
