"""Public Apple listing lookup validation tests."""

from datetime import UTC, datetime

import httpx
import pytest

from local_aso_tracker.apple.client import AppleClientError
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
from local_aso_tracker.services.coverage import analyze_distribution_strategy
from local_aso_tracker.services.health import assess_listing


def listing_payload(app_id: int = 6771773264) -> dict[str, object]:
    return {
        "resultCount": 1,
        "results": [
            {
                "trackId": app_id,
                "trackName": "Learn Astrology: AstroLingo",
                "bundleId": "app.astrolingo.mobile",
                "description": "A" * 800,
                "screenshotUrls": ["one", "two", "three"],
                "averageUserRating": 4.8,
                "userRatingCount": 30,
                "currentVersionReleaseDate": "2026-07-01T00:00:00Z",
                "languageCodesISO2A": ["EN", "FR"],
                "fileSizeBytes": "200000000",
            }
        ],
    }


def test_listing_lookup_uses_public_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id"] == "6771773264"
        assert request.url.params["country"] == "us"
        return httpx.Response(200, json=listing_payload(), request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        listing = lookup_listing(6771773264, "US", client=client)
    assert listing.track_name == "Learn Astrology: AstroLingo"
    assert listing.file_size_bytes == 200000000
    assert listing.screenshot_count == 3


def test_listing_lookup_reports_unknown_app() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resultCount": 0, "results": []}, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(AppleClientError, match="no public listing"),
    ):
        lookup_listing(999, "us", client=client)


def test_health_score_is_explainable_and_bounded() -> None:
    listing = AppleListing.model_validate(listing_payload()["results"][0])  # type: ignore[index]
    strategy = analyze_distribution_strategy(
        "Learn Astrology: AstroLingo",
        "Natal guidance",
        "zodiac, houses",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )
    health = assess_listing(
        listing,
        now=datetime(2026, 7, 12, tzinfo=UTC),
        strategy=strategy,
    )
    assert health.score == sum(item.score for item in health.items)
    assert health.score == 100
    assert {item.key for item in health.items} == {"keyword_repetition", "title_order"}
    assert "Public listing fields are not scored" in str(health.as_dict()["methodology"])
    without_audit = assess_listing(listing)
    assert without_audit.score is None
    assert without_audit.items == []


def test_missing_public_screenshot_urls_do_not_affect_strategy_score() -> None:
    payload = listing_payload()["results"][0]  # type: ignore[index]
    assert isinstance(payload, dict)
    payload["screenshotUrls"] = []
    listing_without_screenshots = AppleListing.model_validate(payload)
    listing_with_screenshots = AppleListing.model_validate(
        listing_payload()["results"][0]  # type: ignore[index]
    )
    strategy = analyze_distribution_strategy(
        "Learn Astrology: AstroLingo",
        "Natal guidance",
        "zodiac, houses",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )

    without_screenshots = assess_listing(listing_without_screenshots, strategy=strategy)
    with_screenshots = assess_listing(listing_with_screenshots, strategy=strategy)

    assert without_screenshots.score == with_screenshots.score == 100
    assert "screenshots" not in {item.key for item in without_screenshots.items}


def test_keyword_coverage_repetition_lowers_listing_health_score() -> None:
    listing = AppleListing.model_validate(listing_payload()["results"][0])  # type: ignore[index]
    clean_strategy = analyze_distribution_strategy(
        "Learn Astrology: AstroLingo",
        "Natal guidance",
        "zodiac, houses",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )
    repeated_strategy = analyze_distribution_strategy(
        "Learn Astrology: AstroLingo",
        "Astrology guide",
        "astrology, birth chart",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )
    wrong_order_strategy = analyze_distribution_strategy(
        "AstroLingo: Learn Astrology",
        "Natal guidance",
        "zodiac, houses",
        goal="aso_seo_aeo",
        brand_term="AstroLingo",
    )

    clean_health = assess_listing(
        listing,
        now=datetime(2026, 7, 12, tzinfo=UTC),
        strategy=clean_strategy,
    )
    repeated_health = assess_listing(
        listing,
        now=datetime(2026, 7, 12, tzinfo=UTC),
        strategy=repeated_strategy,
    )
    wrong_order_health = assess_listing(
        listing,
        now=datetime(2026, 7, 12, tzinfo=UTC),
        strategy=wrong_order_strategy,
    )
    clean_repetition = next(item for item in clean_health.items if item.key == "keyword_repetition")
    repeated_repetition = next(
        item for item in repeated_health.items if item.key == "keyword_repetition"
    )
    wrong_order_title = next(item for item in wrong_order_health.items if item.key == "title_order")

    assert clean_health.score == 100
    assert clean_repetition.score == 70
    assert repeated_repetition.score < clean_repetition.score
    assert wrong_order_title.score == 0
    assert repeated_health.score < clean_health.score
    assert wrong_order_health.score < clean_health.score
    assert "repeated" in repeated_repetition.detail.lower()
    assert any("repeated meaningful keywords" in item for item in repeated_health.suggestions)
