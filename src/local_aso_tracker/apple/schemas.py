"""Validated schemas for the public iTunes Search API."""

from pydantic import BaseModel, ConfigDict, Field


class AppleSoftwareResult(BaseModel):
    """The subset of a software search result used by the tracker."""

    model_config = ConfigDict(extra="ignore")

    track_id: int = Field(alias="trackId")
    track_name: str | None = Field(default=None, alias="trackName")
    version: str | None = None
    track_view_url: str | None = Field(default=None, alias="trackViewUrl")
    artwork_url_100: str | None = Field(default=None, alias="artworkUrl100")
    user_rating_count: int | None = Field(default=None, alias="userRatingCount", ge=0)
    average_user_rating: float | None = Field(default=None, alias="averageUserRating", ge=0, le=5)


class AppleSearchResponse(BaseModel):
    """Top-level Apple search response."""

    model_config = ConfigDict(extra="ignore")

    result_count: int = Field(alias="resultCount", ge=0)
    results: list[AppleSoftwareResult]
