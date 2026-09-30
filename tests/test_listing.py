"""Public Apple listing lookup validation tests."""

from datetime import UTC, datetime

import httpx
import pytest

from local_aso_tracker.apple.client import AppleClientError
from local_aso_tracker.apple.listing import AppleListing, lookup_listing
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
    health = assess_listing(listing, now=datetime(2026, 7, 12, tzinfo=UTC))
    assert health.score == sum(item.score for item in health.items)
    assert 0 <= health.score <= 100
    assert {item.key for item in health.items} == {
        "title",
        "description",
        "screenshots",
        "ratings",
        "freshness",
        "localization",
    }
    assert "not an Apple score" in str(health.as_dict()["methodology"])


def test_missing_public_screenshot_urls_are_unavailable_not_zero() -> None:
    payload = listing_payload()["results"][0]  # type: ignore[index]
    assert isinstance(payload, dict)
    payload["screenshotUrls"] = []
    listing = AppleListing.model_validate(payload)

    health = assess_listing(listing, now=datetime(2026, 7, 12, tzinfo=UTC))
    screenshot = next(item for item in health.items if item.key == "screenshots")

    assert screenshot.available is False
    assert "unknown" in screenshot.detail.lower()
    assert health.score > sum(item.score for item in health.items)
