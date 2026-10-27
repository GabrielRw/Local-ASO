"""Apple Ads persistence and service composition tests."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from local_aso_tracker.apple.ads import (
    AppleAdsAccountRecord,
    AppleAdsCampaignRecord,
    AppleAdsKeywordRecord,
    AppleAdsMetricRecord,
    AppleAdsSuggestionRecord,
)
from local_aso_tracker.config import update_settings
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import RankCheck
from local_aso_tracker.repositories.apple_ads import apple_ads_payload
from local_aso_tracker.repositories.data import (
    list_targets,
    seed_catalog,
    seed_targets,
)
from local_aso_tracker.services.apple_ads import sync_apple_ads


class FakeAppleAdsClient:
    def credential_status(self) -> dict[str, object]:
        return {"available": True, "private_permissions": True, "path": "/local/secret"}

    def accounts(self) -> list[AppleAdsAccountRecord]:
        return [AppleAdsAccountRecord(22024640, 42, "Example Ads", ("API Campaign Manager",))]

    def campaigns(self, _account_id: int) -> list[AppleAdsCampaignRecord]:
        return [
            AppleAdsCampaignRecord(
                campaign_id=11,
                name="US Exact",
                status="ENABLED",
                promoted_object_id=6771773264,
                promoted_object_type="APPSTORE_APP",
                countries=("US",),
                deleted=False,
            )
        ]

    def keywords(
        self,
        _account_id: int,
        _campaigns: list[AppleAdsCampaignRecord],
    ) -> list[AppleAdsKeywordRecord]:
        return [
            AppleAdsKeywordRecord(
                keyword_id=21,
                campaign_id=11,
                ad_group_id=31,
                ad_group_name="Core",
                text="learn astrology",
                match_type="EXACT",
                status="ENABLED",
                display_status="RUNNING",
                bid_amount=Decimal("0.80"),
                bid_currency="EUR",
                deleted=False,
            )
        ]

    def keyword_metrics(
        self,
        _account_id: int,
        _campaigns: list[AppleAdsCampaignRecord],
        *,
        start: date,
        end: date,
    ) -> list[AppleAdsMetricRecord]:
        return [
            AppleAdsMetricRecord(
                keyword_id=21,
                metric_date=end,
                country_or_region="US",
                device_class="iPhone",
                impressions=100,
                taps=4,
                local_spend=Decimal("1.60"),
                currency="EUR",
                tap_installs=2,
                total_installs=3,
                ttr=Decimal("0.04"),
                cpt=Decimal("0.40"),
                suggested_bid=Decimal("1.20"),
            )
        ]

    def keyword_suggestions(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> list[AppleAdsSuggestionRecord]:
        return [AppleAdsSuggestionRecord("astrology birth chart", 14)]


@pytest.fixture
def ads_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    update_settings(apple_ads_account_id=22024640)
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)
        target = list_targets(
            session,
            apple_id=6771773264,
            keyword="learn astrology",
            country="us",
            device="iphone",
        )[0]
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=1,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            )
        )


def test_apple_ads_sync_persists_keywords_metrics_and_suggestions(
    ads_database: None,
) -> None:
    payload = sync_apple_ads(
        apple_app_id=6771773264,
        country="us",
        device="iphone",
        days=30,
        client=FakeAppleAdsClient(),  # type: ignore[arg-type]
    )

    assert payload["selectedAccountId"] == 22024640
    assert payload["allMarketsSummary"]["spend"] == "1.6"  # type: ignore[index]
    assert payload["summary"]["spend"] == "1.6"  # type: ignore[index]
    assert payload["summary"]["tapInstalls"] == 2  # type: ignore[index]
    assert payload["keywords"][0]["asoRank"] == 1  # type: ignore[index]
    assert payload["keywordCountries"][0]["code"] == "US"  # type: ignore[index]
    assert payload["keywordCountries"][0]["keywords"][0]["country"] == "US"  # type: ignore[index]
    assert payload["suggestions"][0]["popularity"] == 14  # type: ignore[index]
    assert payload["sync"]["keywords"] == 1  # type: ignore[index]


def test_apple_ads_payload_is_empty_without_a_selected_account(ads_database: None) -> None:
    update_settings(apple_ads_account_id=0)
    with session_scope() as session:
        payload = apple_ads_payload(
            session,
            apple_app_id=6771773264,
            country="us",
            device="iphone",
            selected_account_id=0,
            days=30,
            start=date(2026, 9, 27),
            end=date(2026, 10, 26),
        )
    assert payload["selectedAccountId"] is None
    assert payload["keywords"] == []
