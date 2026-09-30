"""Public Apple lookup client for listing metadata used by the local dashboard."""

from __future__ import annotations

import time
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from local_aso_tracker.apple.client import USER_AGENT, AppleClientError, MalformedAppleResponse
from local_aso_tracker.config import validate_country_code

APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup"


class AppleListing(BaseModel):
    """Public App Store listing fields exposed by Apple's lookup endpoint."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    track_id: int = Field(alias="trackId")
    track_name: str = Field(alias="trackName")
    bundle_id: str | None = Field(default=None, alias="bundleId")
    seller_name: str | None = Field(default=None, alias="sellerName")
    version: str | None = None
    track_view_url: str | None = Field(default=None, alias="trackViewUrl")
    artwork_url: str | None = Field(default=None, alias="artworkUrl100")
    genre: str | None = Field(default=None, alias="primaryGenreName")
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list, alias="screenshotUrls")
    ipad_screenshot_urls: list[str] = Field(default_factory=list, alias="ipadScreenshotUrls")
    average_rating: float | None = Field(default=None, alias="averageUserRating")
    rating_count: int = Field(default=0, alias="userRatingCount")
    current_version_release_date: datetime | None = Field(
        default=None, alias="currentVersionReleaseDate"
    )
    release_date: datetime | None = Field(default=None, alias="releaseDate")
    language_codes: list[str] = Field(default_factory=list, alias="languageCodesISO2A")
    file_size_bytes: int | None = Field(default=None, alias="fileSizeBytes")
    formatted_price: str | None = Field(default=None, alias="formattedPrice")
    minimum_os_version: str | None = Field(default=None, alias="minimumOsVersion")

    @property
    def screenshot_count(self) -> int:
        return len(self.screenshot_urls) + len(self.ipad_screenshot_urls)


class AppleLookupResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result_count: int = Field(alias="resultCount", ge=0)
    results: list[AppleListing]


def lookup_listing(
    apple_app_id: int,
    country: str,
    *,
    timeout: float = 15.0,
    retry_count: int = 3,
    client: httpx.Client | None = None,
) -> AppleListing:
    """Retrieve one app's public listing with conservative transient retries."""

    storefront = validate_country_code(country)
    owned = client is None
    http = client or httpx.Client(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        for attempt in range(retry_count + 1):
            try:
                response = http.get(
                    APPLE_LOOKUP_URL,
                    params={"id": apple_app_id, "country": storefront, "entity": "software"},
                )
                response.raise_for_status()
                parsed = AppleLookupResponse.model_validate(response.json())
                if parsed.result_count < 1 or not parsed.results:
                    raise AppleClientError(
                        f"Apple has no public listing for app {apple_app_id} in {storefront}"
                    )
                return parsed.results[0]
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                retryable = True
                error: Exception = exc
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                error = exc
            except (ValidationError, ValueError, TypeError) as exc:
                raise MalformedAppleResponse(f"malformed Apple lookup response: {exc}") from exc
            if not retryable or attempt >= retry_count:
                raise AppleClientError(f"Apple listing lookup failed: {error}") from error
            time.sleep(min(2**attempt, 4))
    finally:
        if owned:
            http.close()
    raise AssertionError("lookup retry loop exhausted unexpectedly")
