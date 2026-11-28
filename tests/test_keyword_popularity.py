"""Apple Ads keyword popularity measurement tests (Apple is always mocked)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from local_aso_tracker.apple.ads import (
    AppleAdsCampaignRecord,
    AppleAdsError,
    AppleAdsSuggestionRecord,
)
from local_aso_tracker.config import update_settings
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import KeywordPopularity
from local_aso_tracker.repositories.data import add_app, list_targets, seed_catalog, seed_targets
from local_aso_tracker.services.keyword_popularity import (
    exact_popularity,
    refresh_keyword_popularity,
)

PROMOTED_APP_ID = 6771773264


class FakeClient:
    """Answers like Apple: the requested term first, then related terms on its scale."""

    def __init__(
        self, scores: dict[str, int | None], *, fail: bool = False, campaigns: bool = True
    ) -> None:
        self.scores = scores
        self.fail = fail
        self.has_campaigns = campaigns
        self.requests: list[tuple[str, str, int]] = []

    def campaigns(self, _account_id: int) -> list[AppleAdsCampaignRecord]:
        if not self.has_campaigns:
            return []
        return [
            AppleAdsCampaignRecord(
                campaign_id=1,
                name="Any",
                status="ENABLED",
                promoted_object_id=PROMOTED_APP_ID,
                promoted_object_type="APPSTORE_APP",
                countries=("US",),
                deleted=False,
            )
        ]

    def keyword_suggestions(
        self,
        _account_id: int,
        *,
        apple_app_id: int,
        country: str,
        terms: list[str],
        limit: int = 100,
    ) -> list[AppleAdsSuggestionRecord]:
        if self.fail:
            raise AppleAdsError("Apple Ads is unavailable")
        term = terms[0]
        self.requests.append((term, country, apple_app_id))
        related = [AppleAdsSuggestionRecord(f"{term} app", 90)]
        score = self.scores.get(term.casefold(), 5)
        if score is None:
            return related
        return [AppleAdsSuggestionRecord(f"  {term.title()} ", score), *related]


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    update_settings(apple_ads_account_id=22024640)
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)


def _us_keywords() -> set[str]:
    with session_scope() as session:
        return {
            target.keyword.normalized_keyword
            for target in list_targets(session, country="us", active_only=True)
        }


def _stored() -> dict[tuple[str, str], int | None]:
    with session_scope() as session:
        return {
            (row.normalized_keyword, row.country_code): row.popularity
            for row in session.scalars(select(KeywordPopularity))
        }


def test_exact_popularity_ignores_relative_suggestions() -> None:
    suggestions = [
        AppleAdsSuggestionRecord("astrology app", 80),
        AppleAdsSuggestionRecord("Learn  Astrology", 22),
    ]
    assert exact_popularity(suggestions, "learn astrology") == (True, 22)
    assert exact_popularity(suggestions[:1], "learn astrology") == (False, None)


def test_refresh_stores_exact_values_and_missing_terms(database: None) -> None:
    keywords = _us_keywords()
    missing = sorted(keywords)[0]
    client = FakeClient({"learn astrology": 22, missing: None})

    summary = refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]

    stored = _stored()
    assert {key for key, _ in stored} == keywords
    assert {country for _, country in stored} == {"US"}
    assert stored[("learn astrology", "US")] == 22
    # Apple had no exact match: remembered as empty, never the related term's 90.
    assert stored[(missing, "US")] is None
    assert 90 not in stored.values()
    assert summary.missing == 1
    assert summary.measured == len(keywords) - 1
    assert all(app_id == PROMOTED_APP_ID for _, _, app_id in client.requests)


def test_refresh_waits_seven_days_unless_forced(database: None) -> None:
    client = FakeClient({})
    refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]
    first_requests = len(client.requests)

    again = refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]
    assert again.requested == 0
    assert again.skipped == first_requests

    later = datetime.now(UTC) + timedelta(days=8)
    stale = refresh_keyword_popularity(country="us", client=client, now=later)  # type: ignore[arg-type]
    assert stale.requested == first_requests

    forced = refresh_keyword_popularity(country="us", client=client, force=True, now=later)  # type: ignore[arg-type]
    assert forced.requested == first_requests


def test_refresh_requires_a_selected_account(database: None) -> None:
    update_settings(apple_ads_account_id=0)
    with pytest.raises(ValueError, match="select an Apple Ads account"):
        refresh_keyword_popularity(client=FakeClient({}))  # type: ignore[arg-type]


def test_refresh_without_campaigns_asks_for_a_tracked_app(database: None) -> None:
    # An account that never ran a campaign still gets popularity for an app it owns.
    with session_scope() as session:
        add_app(session, "Second app", 6700000001)
    update_settings(default_app_id=6700000001)
    client = FakeClient({}, campaigns=False)

    summary = refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]

    assert summary.measured == len(_us_keywords())
    assert {app_id for _, _, app_id in client.requests} == {6700000001}


def test_refresh_without_campaigns_falls_back_to_the_first_tracked_app(database: None) -> None:
    update_settings(default_app_id=6700000002)  # not tracked
    client = FakeClient({}, campaigns=False)

    refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]

    assert {app_id for _, _, app_id in client.requests} == {PROMOTED_APP_ID}


def test_refresh_stops_after_repeated_apple_failures(database: None) -> None:
    summary = refresh_keyword_popularity(country="us", client=FakeClient({}, fail=True))  # type: ignore[arg-type]
    assert summary.failures == 3
    assert summary.measured == 0
    assert _stored() == {}


def test_dashboard_rankings_carry_measured_and_unavailable_popularity(database: None) -> None:
    from local_aso_tracker.models import RankCheck
    from local_aso_tracker.repositories.data import latest_pairs
    from local_aso_tracker.services.analytics import RankingRow
    from local_aso_tracker.web.server import DashboardService

    with session_scope() as session:
        targets = list_targets(session, country="us", device="iphone", active_only=True)[:2]
        for target in targets:
            session.add(
                RankCheck(
                    tracking_target_id=target.id,
                    checked_at=datetime.now(UTC),
                    rank=None,
                    found=False,
                    result_limit=200,
                    response_time_ms=1,
                    status="success",
                )
            )
        session.flush()
        measured, unavailable = (target.keyword.normalized_keyword for target in targets)
        session.add(KeywordPopularity(normalized_keyword=measured, country_code="US", popularity=5))
        session.add(KeywordPopularity(normalized_keyword=unavailable, country_code="US"))
        session.flush()
        pairs = latest_pairs(session, targets)
        rows = [RankingRow(target, *pairs[target.id]) for target in targets]
        payload = DashboardService._rankings(session, rows)

    by_status = {item["popularityStatus"]: item["popularity"] for item in payload}
    assert by_status == {"measured": 5, "unavailable": None}


def test_refresh_skips_storefronts_apple_ads_does_not_serve(database: None) -> None:
    class UnsupportedMarketClient(FakeClient):
        def keyword_suggestions(
            self, *args: object, **kwargs: object
        ) -> list[AppleAdsSuggestionRecord]:
            if kwargs["country"] == "US":
                raise AppleAdsError(
                    "Apple Ads API returned HTTP 400: INVALID_INPUT countriesOrRegions "
                    "Invalid storefront name:US"
                )
            return super().keyword_suggestions(*args, **kwargs)  # type: ignore[arg-type]

    client = UnsupportedMarketClient({})
    summary = refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]
    assert summary.unsupported_markets == ("US",)
    assert summary.failures == 0
    assert _stored() == {}


def test_unsupported_storefronts_are_remembered_and_not_asked_again(
    database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from local_aso_tracker.models import RankCheck
    from local_aso_tracker.repositories.data import latest_pairs
    from local_aso_tracker.repositories.keyword_popularity import unsupported_markets
    from local_aso_tracker.services.analytics import RankingRow
    from local_aso_tracker.web import server

    calls: list[str] = []

    class UnsupportedMarketClient(FakeClient):
        def keyword_suggestions(
            self, *args: object, **kwargs: object
        ) -> list[AppleAdsSuggestionRecord]:
            calls.append(str(kwargs["country"]))
            raise AppleAdsError(
                "Apple Ads API returned HTTP 400: INVALID_INPUT countriesOrRegions "
                "Invalid storefront name:US"
            )

    client = UnsupportedMarketClient({})
    refresh_keyword_popularity(country="us", client=client)  # type: ignore[arg-type]
    assert calls == ["US"]
    with session_scope() as session:
        assert unsupported_markets(session) == {"US"}

    # Within the refresh window the storefront is skipped without asking Apple again.
    summary = refresh_keyword_popularity(country="us", client=client, force=True)  # type: ignore[arg-type]
    assert calls == ["US"] and summary.requested == 0

    # The dashboard then reports "unsupported", so the local estimate is shown there.
    with session_scope() as session:
        target = list_targets(session, country="us", device="iphone", active_only=True)[0]
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=None,
                found=False,
                result_limit=200,
                response_time_ms=1,
                status="success",
            )
        )
        session.flush()
        rows = [RankingRow(target, *latest_pairs(session, [target])[target.id])]
        monkeypatch.setattr(server, "popularity_configured", lambda: True)
        status = server.DashboardService._rankings(session, rows)[0]["popularityStatus"]
        assert status == "unsupported"


def test_dashboard_rankings_mark_unmeasured_popularity_pending_with_apple_ads(
    database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from local_aso_tracker.models import RankCheck
    from local_aso_tracker.repositories.data import latest_pairs
    from local_aso_tracker.services.analytics import RankingRow
    from local_aso_tracker.web import server

    with session_scope() as session:
        target = list_targets(session, country="us", device="iphone", active_only=True)[0]
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=None,
                found=False,
                result_limit=200,
                response_time_ms=1,
                status="success",
            )
        )
        session.flush()
        rows = [RankingRow(target, *latest_pairs(session, [target])[target.id])]

        # Apple Ads connected, keyword not asked yet: "pending", so no estimate stands in.
        monkeypatch.setattr(server, "popularity_configured", lambda: True)
        assert server.DashboardService._rankings(session, rows)[0]["popularityStatus"] == "pending"

        # Without Apple Ads, None: the dashboard may show the local estimate.
        monkeypatch.setattr(server, "popularity_configured", lambda: False)
        assert server.DashboardService._rankings(session, rows)[0]["popularityStatus"] is None


def test_dashboard_rankings_carry_the_opportunity_score(database: None) -> None:
    from local_aso_tracker.models import RankCheck, RankEstimate
    from local_aso_tracker.repositories.data import latest_pairs
    from local_aso_tracker.services.analytics import RankingRow
    from local_aso_tracker.web.server import DashboardService

    with session_scope() as session:
        targets = list_targets(session, country="us", device="iphone", active_only=True)[:4]
        # (rank, found, difficulty, Apple popularity)
        cases = [
            (2, True, 40, 50),
            (None, False, 40, 50),
            (None, False, None, 50),
            (3, True, 40, None),
        ]
        for target, (rank, found, difficulty, popularity) in zip(targets, cases, strict=True):
            check = RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=rank,
                found=found,
                result_limit=200,
                response_time_ms=1,
                status="success",
            )
            if difficulty is not None:
                check.estimate = RankEstimate(
                    volume=None, difficulty=difficulty, sample_size=10, model_version="test"
                )
            session.add(check)
            session.add(
                KeywordPopularity(
                    normalized_keyword=target.keyword.normalized_keyword,
                    country_code="US",
                    popularity=popularity,
                )
            )
        session.flush()
        pairs = latest_pairs(session, targets)
        rows = [RankingRow(target, *pairs[target.id]) for target in targets]
        payload = DashboardService._rankings(session, rows)

    # 50 x (100 - 40) / 100 = 30 to win; #2 already captures 2^-1.2 of it.
    # Never a score without Apple's popularity or a difficulty estimate.
    assert [item["opportunity"] for item in payload] == [17, 30, None, None]
