"""Local dashboard composition and mutation tests."""

from datetime import UTC, datetime
from pathlib import Path
from threading import Thread

import httpx
import pytest
from sqlalchemy import select

from local_aso_tracker.apple.listing import AppleListing
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import RankCheck, RankTopApp, Storefront
from local_aso_tracker.repositories.data import (
    add_app,
    list_targets,
    seed_catalog,
    seed_targets,
    successful_checks,
)
from local_aso_tracker.services.checks import CheckRunResult
from local_aso_tracker.web.server import DashboardHandler, DashboardService, LocalDashboardServer


def sample_listing(
    app_id: int = 6771773264, name: str = "Learn Astrology: AstroLingo"
) -> AppleListing:
    return AppleListing.model_validate(
        {
            "trackId": app_id,
            "trackName": name,
            "bundleId": f"example.{app_id}",
            "artworkUrl100": f"https://is1-ssl.mzstatic.com/{app_id}/icon.png",
            "description": "Structured astrology lessons and quizzes. " * 30,
            "screenshotUrls": ["one", "two", "three", "four", "five"],
            "averageUserRating": 4.7,
            "userRatingCount": 42,
            "currentVersionReleaseDate": "2026-07-01T00:00:00Z",
            "languageCodesISO2A": ["EN", "FR"],
            "primaryGenreName": "Education",
            "version": "1.2",
        }
    )


@pytest.fixture
def dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DashboardService:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)
        target = list_targets(
            session,
            apple_id=6771773264,
            keyword="learn astrology",
            country="us",
        )[0]
        check = RankCheck(
            tracking_target_id=target.id,
            checked_at=datetime.now(UTC),
            rank=26,
            found=True,
            result_limit=200,
            total_results_reported=186,
            response_time_ms=100,
            status="success",
        )
        check.top_apps = [
            RankTopApp(
                position=1,
                track_id=111,
                name="First app",
                artwork_url="https://is1-ssl.mzstatic.com/first.png",
            ),
            RankTopApp(
                position=2,
                track_id=222,
                name="Second app",
                artwork_url=None,
            ),
        ]
        session.add(check)
    service = DashboardService()
    monkeypatch.setattr(service, "listing", lambda app_id, country: sample_listing(app_id))

    def fake_run_checks(session, targets, settings):  # type: ignore[no-untyped-def]
        checks = []
        for target in targets:
            check = RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=9,
                found=True,
                result_limit=settings.result_limit,
                total_results_reported=100,
                response_time_ms=10,
                status="success",
            )
            session.add(check)
            checks.append(check)
        session.flush()
        searches = len(
            {
                (target.keyword.keyword, target.storefront.country_code, target.device)
                for target in targets
            }
        )
        return CheckRunResult(checks=checks, searches=searches, failures=0)

    monkeypatch.setattr("local_aso_tracker.web.server.run_checks", fake_run_checks)
    return service


def test_dashboard_bootstrap_uses_real_local_rank_data(dashboard: DashboardService) -> None:
    payload = dashboard.bootstrap(6771773264, "us")
    assert payload["selectedAppId"] == 6771773264
    assert len(payload["apps"]) == 1  # type: ignore[arg-type]
    rankings = payload["rankings"]
    assert isinstance(rankings, list)
    assert rankings[0]["rank"] == 26
    assert rankings[0]["opportunity"] == "Growth opportunities (21-50)"
    assert payload["targetCounts"]["us:iphone"] == 15  # type: ignore[index]
    assert payload["targetCounts"]["us:ipad"] == 0  # type: ignore[index]
    assert "us:iphone" in payload["metricTrends"]  # type: ignore[operator]
    assert "us:iphone" in payload["metricTrends30d"]  # type: ignore[operator]
    assert rankings[0]["device"] == "iphone"
    assert rankings[0]["topApps"][0]["name"] == "First app"  # type: ignore[index]
    assert rankings[0]["topApps"][1]["appId"] == 222  # type: ignore[index]
    assert payload["health"]["score"] > 0  # type: ignore[index]
    assert payload["listing"]["screenshotStatus"] == "available"  # type: ignore[index]
    assert len(payload["listing"]["screenshots"]) == 5  # type: ignore[index]
    assert payload["apps"][0]["artworkUrl"] == (  # type: ignore[index]
        "https://is1-ssl.mzstatic.com/6771773264/icon.png"
    )


def test_dashboard_adds_keyword_targets_and_soft_deactivates(
    dashboard: DashboardService,
) -> None:
    result = dashboard.add_keyword_targets(
        {"appId": 6771773264, "keyword": "astro transits", "countries": ["us", "fr"]}
    )
    assert result["targetsCreated"] == 2
    assert result["automaticCheck"] == {"checks": 2, "searches": 2, "failures": 0}
    with session_scope() as session:
        target = list_targets(
            session,
            apple_id=6771773264,
            keyword="astro transits",
            country="us",
        )[0]
        assert len(successful_checks(session, [target])) == 1
        target_id = target.id
    assert dashboard.deactivate_target({"targetId": target_id}) == {"deactivated": target_id}
    with session_scope() as session:
        target = list_targets(
            session,
            apple_id=6771773264,
            keyword="astro transits",
            country="us",
        )[0]
        assert target.active is False
    reactivated = dashboard.add_keyword_targets(
        {"appId": 6771773264, "keyword": "astro transits", "countries": ["us"]}
    )
    assert reactivated["targetsCreated"] == 0
    assert reactivated["targetsReactivated"] == 1


def test_dashboard_exposes_visibility_for_every_tracked_country(
    dashboard: DashboardService,
) -> None:
    result = dashboard.add_keyword_targets(
        {
            "appId": 6771773264,
            "keyword": "astrology for beginners",
            "countries": ["us", "fr"],
            "devices": ["iphone"],
        }
    )
    assert result["automaticCheck"] == {"checks": 2, "searches": 2, "failures": 0}

    payload = dashboard.bootstrap(6771773264, "us")
    assert payload["targetCounts"]["us:iphone"] > 0  # type: ignore[index]
    assert payload["targetCounts"]["fr:iphone"] > 0  # type: ignore[index]
    country_rows = {
        row["country"]
        for row in payload["rankings"]  # type: ignore[union-attr]
        if row["device"] == "iphone" and row["found"] and row["rank"] <= 10
    }
    assert country_rows == {"us", "fr"}


def test_paid_keyword_rank_search_creates_missing_storefront_and_checks_rank(
    dashboard: DashboardService,
) -> None:
    result = dashboard.check_paid_keyword_rank(
        {
            "appId": 6771773264,
            "keyword": "astrology for beginners",
            "country": "be",
            "countryName": "Belgium",
            "device": "iphone",
        }
    )

    assert result["keyword"] == "astrology for beginners"
    assert result["country"] == "be"
    assert result["device"] == "iphone"
    assert result["automaticCheck"] == {"checks": 1, "searches": 1, "failures": 0}
    assert result["rankCheck"]["rank"] == 9
    with session_scope() as session:
        storefront = session.scalar(select(Storefront).where(Storefront.country_code == "be"))
        target = list_targets(
            session,
            apple_id=6771773264,
            keyword="astrology for beginners",
            country="be",
            device="iphone",
            active_only=True,
        )[0]
        assert storefront is not None and storefront.active is True
        assert successful_checks(session, [target])[0].rank == 9


def test_dashboard_adds_comma_separated_keywords_for_multiple_devices(
    dashboard: DashboardService,
) -> None:
    result = dashboard.add_keyword_targets(
        {
            "appId": 6771773264,
            "keywords": "moon phases, retrograde calendar\nMOON PHASES",
            "countries": ["us", "fr"],
            "devices": ["iphone", "ipad"],
        }
    )

    assert result["keywordsRequested"] == 2
    assert result["keywordsCreated"] == 2
    assert result["targetsCreated"] == 8
    assert result["targetsReactivated"] == 0
    assert result["targetsUnchanged"] == 0
    assert result["automaticCheck"] == {"checks": 8, "searches": 8, "failures": 0}
    with session_scope() as session:
        targets = list_targets(session, keyword="moon phases")
        assert {(target.storefront.country_code, target.device) for target in targets} == {
            ("us", "iphone"),
            ("us", "ipad"),
            ("fr", "iphone"),
            ("fr", "ipad"),
        }


def test_dashboard_localizes_and_adds_market_specific_keyword_groups(
    dashboard: DashboardService,
) -> None:
    localized = dashboard.localize_keywords(
        {"keywords": "birth chart lessons, astrology basics", "countries": ["us", "fr"]}
    )
    groups = localized["groups"]
    assert isinstance(groups, list)
    assert [group["language"] for group in groups] == ["English", "French", "Spanish"]

    result = dashboard.add_keyword_targets(
        {
            "appId": 6771773264,
            "groups": [
                {
                    "keywords": group["keywords"],
                    "countries": group["countries"],
                }
                for group in groups
            ],
            "devices": ["iphone"],
        }
    )
    assert result["targetsCreated"] == 6
    assert result["targetsUnchanged"] == 0
    assert result["automaticCheck"] == {"checks": 6, "searches": 6, "failures": 0}
    with session_scope() as session:
        english = list_targets(session, keyword="birth chart lessons")
        french = list_targets(session, keyword="leçons de thème astral")
        spanish = list_targets(session, keyword="lecciones de carta natal")
        assert {target.storefront.country_code for target in english} == {"us"}
        assert {target.storefront.country_code for target in french} == {"fr"}
        assert {target.storefront.country_code for target in spanish} == {"us"}


def test_dashboard_compares_two_public_listings(
    dashboard: DashboardService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dashboard,
        "listing",
        lambda app_id, country: sample_listing(app_id, "Primary" if app_id == 1 else "Other"),
    )
    result = dashboard.compare(1, 2, "us")
    assert result["primary"]["name"] == "Primary"  # type: ignore[index]
    assert result["competitor"]["name"] == "Other"  # type: ignore[index]
    assert result["primaryHealth"]["score"] == result["competitorHealth"]["score"]  # type: ignore[index]


def test_dashboard_saves_and_analyzes_listing_metadata(dashboard: DashboardService) -> None:
    result = dashboard.save_listing_coverage(
        {
            "appId": 6771773264,
            "country": "us",
            "device": "iphone",
            "name": "Learn Astrology",
            "subtitle": "Birth Chart Lessons",
            "keywords": "birth chart, natal chart, astrology",
        }
    )

    assert result["metadata"]["name"] == "Learn Astrology"  # type: ignore[index]
    assert result["analysis"]["tracked_matches"] == 1  # type: ignore[index]
    assert result["analysis"]["ranked_keywords"] == 1  # type: ignore[index]
    payload = dashboard.bootstrap(6771773264, "us")
    assert payload["listingMetadata"]["subtitle"] == "Birth Chart Lessons"  # type: ignore[index]


def test_dashboard_removes_app_and_can_restore_it_by_re_adding(
    dashboard: DashboardService,
) -> None:
    with session_scope() as session:
        add_app(session, "Another app", 123)

    result = dashboard.deactivate_app({"appleId": 6771773264})
    assert result == {"removed": 6771773264, "name": "AstroLingo"}
    payload = dashboard.bootstrap(6771773264, "us")
    assert payload["selectedAppId"] == 123
    assert sum(item["active"] for item in payload["apps"]) == 1  # type: ignore[index]

    with session_scope() as session:
        assert len(session.scalars(select(RankCheck)).all()) == 1

    restored = dashboard.add_app_from_apple({"appleId": 6771773264, "country": "us"})
    assert restored["created"] is False
    assert dashboard.bootstrap(6771773264, "us")["selectedAppId"] == 6771773264


def test_dashboard_payload_has_no_retired_metrics(dashboard: DashboardService) -> None:
    payload = dashboard.bootstrap(6771773264, "us")
    assert "appleAds" not in payload
    assert "listingAudit" not in payload
    for ranking in payload["rankings"]:  # type: ignore[union-attr]
        assert not any(key.startswith("popularity") for key in ranking)


def test_retired_feature_endpoints_return_not_found(dashboard: DashboardService) -> None:
    class TestHandler(DashboardHandler):
        service = dashboard

    server = LocalDashboardServer(("127.0.0.1", 0), TestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            for action in ("connect", "verify", "disconnect"):
                response = client.post(f"/api/apple-ads/{action}", json={})
                assert response.status_code == 404
            assert client.post("/api/listing-audit", json={}).status_code == 404
            response = client.get("/api/apple-ads/discovered?appId=6771773264&country=us")
            assert response.status_code == 404
            assert client.get("/api/bootstrap?appId=6771773264&country=us").status_code == 200
            ads = client.get("/api/apple-ads?appId=6771773264&country=us&device=iphone")
            assert ads.status_code == 200
            assert ads.json()["credentials"]["available"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
