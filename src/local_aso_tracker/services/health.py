"""Transparent health scoring based on the saved listing strategy audit."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from local_aso_tracker.apple.listing import AppleListing
from local_aso_tracker.services.coverage import DistributionStrategyAnalysis


@dataclass(frozen=True)
class HealthItem:
    key: str
    label: str
    score: int
    maximum: int
    detail: str
    available: bool = True


@dataclass(frozen=True)
class ListingHealth:
    score: int | None
    label: str
    items: list[HealthItem]
    suggestions: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "label": self.label,
            "items": [asdict(item) for item in self.items],
            "suggestions": self.suggestions,
            "methodology": (
                "A 100-point local listing strategy score. Up to 70 points come from avoiding "
                "repeated meaningful words across Name, Subtitle, and Keywords. Up to 30 points "
                "come from the goal-specific title order. Public listing fields are not scored."
            ),
        }


def assess_listing(
    listing: AppleListing,
    *,
    now: datetime | None = None,
    strategy: DistributionStrategyAnalysis | None = None,
) -> ListingHealth:
    """Score only the saved listing strategy audit."""

    current = now or datetime.now(UTC)
    title_len = len(listing.track_name.strip())
    if 15 <= title_len <= 30:
        title_score, title_detail = 20, f"{title_len}/30 characters; strong keyword room use."
    elif 8 <= title_len <= 30:
        title_score, title_detail = 13, f"{title_len}/30 characters; some room remains."
    else:
        title_score, title_detail = 6, f"{title_len}/30 characters; review the title length."

    description_len = len(listing.description.strip())
    if description_len >= 1_000:
        description_score, description_detail = (
            20,
            f"{description_len:,} characters; substantial copy.",
        )
    elif description_len >= 500:
        description_score, description_detail = (
            15,
            f"{description_len:,} characters; useful but expandable.",
        )
    elif description_len >= 200:
        description_score, description_detail = (
            8,
            f"{description_len:,} characters; relatively brief.",
        )
    else:
        description_score, description_detail = 2, "Description is very short."

    screenshot_count = listing.screenshot_count
    if screenshot_count >= 5:
        screenshot_score, screenshot_detail = (
            20,
            f"{screenshot_count} screenshots returned by Apple.",
        )
    elif screenshot_count >= 3:
        screenshot_score, screenshot_detail = (
            15,
            f"{screenshot_count} screenshots; consider a fuller set.",
        )
    elif screenshot_count:
        screenshot_score, screenshot_detail = 8, f"Only {screenshot_count} screenshot(s) returned."
    else:
        screenshot_score, screenshot_detail = (
            0,
            "Apple's public iTunes API did not expose screenshot URLs. This signal is unknown.",
        )

    if listing.rating_count >= 20 and (listing.average_rating or 0) >= 4.5:
        rating_score, rating_detail = 15, "Strong rating and review signal."
    elif listing.rating_count >= 5 and (listing.average_rating or 0) >= 4:
        rating_score, rating_detail = 10, "Positive rating signal with room to grow."
    elif listing.rating_count:
        label = "rating" if listing.rating_count == 1 else "ratings"
        rating_score, rating_detail = 5, f"Only {listing.rating_count} {label} returned."
    else:
        rating_score, rating_detail = 0, "No rating signal returned in this storefront."

    release = listing.current_version_release_date or listing.release_date
    age_days = (current - release.astimezone(UTC)).days if release else None
    if age_days is not None and age_days <= 90:
        freshness_score, freshness_detail = 15, _updated_detail(max(age_days, 0))
    elif age_days is not None and age_days <= 180:
        freshness_score, freshness_detail = 10, _updated_detail(age_days)
    elif age_days is not None and age_days <= 365:
        freshness_score, freshness_detail = 5, _updated_detail(age_days)
    else:
        freshness_score, freshness_detail = 0, "No recent public release signal."

    locales = len(listing.language_codes)
    localization_score = 10 if locales >= 5 else 6 if locales >= 2 else 3 if locales == 1 else 0
    localization_detail = f"{locales} App Store language code(s) returned."

    public_items = [
        HealthItem("title", "Title", title_score, 20, title_detail),
        HealthItem("description", "Description", description_score, 20, description_detail),
        HealthItem(
            "screenshots",
            "Screenshots",
            screenshot_score,
            20,
            screenshot_detail,
            available=screenshot_count > 0,
        ),
        HealthItem("ratings", "Ratings", rating_score, 15, rating_detail),
        HealthItem("freshness", "Freshness", freshness_score, 15, freshness_detail),
        HealthItem("localization", "Localization", localization_score, 10, localization_detail),
    ]
    public_suggestions = [
        _suggestion(item.key)
        for item in sorted(public_items, key=lambda item: item.score / item.maximum)
        if item.available and item.score < item.maximum
    ]
    if not screenshot_count:
        public_suggestions.insert(
            0,
            "Verify screenshots on the App Store; Apple's public iTunes API did not expose them.",
        )
    public_suggestions = public_suggestions[:4]
    if strategy is None:
        return ListingHealth(
            score=None,
            label="Audit required",
            items=[],
            suggestions=public_suggestions,
        )
    items = [
        _keyword_repetition_health_item(strategy),
        _title_order_health_item(strategy),
    ]
    score = sum(item.score for item in items)
    suggestions = _strategy_suggestions(strategy)
    label = "Strong" if score >= 80 else "Promising" if score >= 65 else "Needs attention"
    return ListingHealth(score=score, label=label, items=items, suggestions=suggestions)


def _keyword_repetition_health_item(strategy: DistributionStrategyAnalysis) -> HealthItem:
    repeated_uses = sum(item.total - 1 for item in strategy.duplicate_words)
    score = max(0, 70 - repeated_uses * 15)
    if strategy.duplicate_words:
        repeated_terms = ", ".join(
            f"{item.word} ({item.total} uses)" for item in strategy.duplicate_words[:4]
        )
        if len(strategy.duplicate_words) > 4:
            repeated_terms += "…"
        repetition_detail = f"{repeated_uses} extra repeated use(s): {repeated_terms}"
    else:
        repetition_detail = "No meaningful word is repeated across indexed fields"
    return HealthItem(
        "keyword_repetition",
        "Keyword repetition",
        score,
        70,
        repetition_detail + ".",
    )


def _title_order_health_item(strategy: DistributionStrategyAnalysis) -> HealthItem:
    title_order = strategy.title_order.passed
    score = 30 if title_order is True else 15 if title_order is None else 0
    return HealthItem(
        "title_order",
        "Title order",
        score,
        30,
        strategy.title_order.detail,
    )


def _strategy_suggestions(strategy: DistributionStrategyAnalysis) -> list[str]:
    suggestions: list[str] = []
    if strategy.duplicate_words:
        words = ", ".join(item.word for item in strategy.duplicate_words[:4])
        suggestions.append(f"Remove repeated meaningful keywords from indexed fields: {words}.")
    if strategy.title_order.passed is False:
        suggestions.append(
            "Adjust the title order to match the selected ASO/SEO/AEO or UGC/Ads strategy."
        )
    if not suggestions:
        suggestions.append(
            "The strategy audit is aligned. Preserve the title order and avoid "
            "repeating indexed terms."
        )
    return suggestions


def _updated_detail(days: int) -> str:
    unit = "day" if days == 1 else "days"
    return f"Updated {days} {unit} ago."


def _suggestion(key: str) -> str:
    return {
        "title": (
            "Review whether the 30-character title allowance can communicate the core "
            "intent more clearly."
        ),
        "description": (
            "Strengthen the description with a clear opening, benefits, and scannable "
            "feature sections."
        ),
        "screenshots": (
            "Check screenshot availability and build a complete visual story for this storefront."
        ),
        "ratings": "Focus on a reliable in-app review prompt after positive user moments.",
        "freshness": (
            "Keep the listing current with meaningful releases and accurate release notes."
        ),
        "localization": (
            "Consider storefront-specific listing localization where the product supports it."
        ),
    }[key]
