"""Ranking movement and summary calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean

from local_aso_tracker.models import RankCheck, TrackingTarget


def movement(current: RankCheck, previous: RankCheck | None) -> str:
    """Describe rank movement, with a lower numeric rank treated as better."""

    if previous is None:
        return "—"
    if current.found and not previous.found:
        return "NEW"
    if not current.found and previous.found:
        return "LOST"
    if not current.found and not previous.found:
        return "—"
    assert current.rank is not None and previous.rank is not None
    delta = previous.rank - current.rank
    return f"{delta:+d}" if delta else "—"


@dataclass(frozen=True)
class RankingRow:
    target: TrackingTarget
    latest: RankCheck
    previous: RankCheck | None

    @property
    def change(self) -> str:
        return movement(self.latest, self.previous)


@dataclass(frozen=True)
class Summary:
    tracked_keywords: int
    top_10: int
    top_20: int
    top_50: int
    top_100: int
    absent: int
    best_keyword: str
    biggest_positive: str
    biggest_negative: str
    newly_ranked: int
    lost: int
    average_rank: float | None


@dataclass(frozen=True)
class MetricTrend:
    current: float
    baseline: float
    percent: float | None
    better: bool | None


@dataclass(frozen=True)
class MetricSnapshot:
    tracked: int
    top_10: int
    top_50: int
    not_visible: int
    average_rank: float | None


def calculate_summary(rows: list[RankingRow]) -> Summary:
    """Calculate visibility metrics from one latest row per target."""

    found = [row for row in rows if row.latest.found and row.latest.rank is not None]
    ranked = [row.latest.rank for row in found if row.latest.rank is not None]
    best = min(found, key=lambda row: row.latest.rank or 10**9) if found else None
    numeric = [(int(row.change), row) for row in rows if row.change not in {"—", "NEW", "LOST"}]
    positive = max(numeric, default=(0, None), key=lambda item: item[0])
    negative = min(numeric, default=(0, None), key=lambda item: item[0])
    return Summary(
        tracked_keywords=len(rows),
        top_10=sum(rank <= 10 for rank in ranked),
        top_20=sum(rank <= 20 for rank in ranked),
        top_50=sum(rank <= 50 for rank in ranked),
        top_100=sum(rank <= 100 for rank in ranked),
        absent=sum(not row.latest.found for row in rows),
        best_keyword=(f"{best.target.keyword.keyword} (#{best.latest.rank})" if best else "—"),
        biggest_positive=_mover_label(positive),
        biggest_negative=_mover_label(negative),
        newly_ranked=sum(row.change == "NEW" for row in rows),
        lost=sum(row.change == "LOST" for row in rows),
        average_rank=fmean(ranked) if ranked else None,
    )


def calculate_metric_trends(
    targets: list[TrackingTarget],
    pairs: dict[int, tuple[RankCheck, RankCheck | None]],
    history: list[RankCheck],
    *,
    cutoff: datetime,
) -> dict[str, dict[str, MetricTrend]]:
    """Compare current portfolio metrics with checks available seven days earlier."""

    cutoff = _utc_aware(cutoff)
    current_checks: dict[str, list[RankCheck]] = {}
    baseline_checks: dict[str, list[RankCheck]] = {}
    current_tracked: dict[str, int] = {}
    baseline_tracked: dict[str, int] = {}
    latest_before_cutoff: dict[int, RankCheck] = {}

    for check in history:
        if _utc_aware(check.checked_at) <= cutoff:
            latest_before_cutoff[check.tracking_target_id] = check

    for target in targets:
        key = f"{target.storefront.country_code}:{target.device}"
        current_tracked[key] = current_tracked.get(key, 0) + 1
        if pair := pairs.get(target.id):
            current_checks.setdefault(key, []).append(pair[0])
        if _utc_aware(target.created_at) <= cutoff:
            baseline_tracked[key] = baseline_tracked.get(key, 0) + 1
            if baseline_check := latest_before_cutoff.get(target.id):
                baseline_checks.setdefault(key, []).append(baseline_check)

    results: dict[str, dict[str, MetricTrend]] = {}
    for key in sorted(set(current_tracked) | set(baseline_tracked)):
        current = _metric_snapshot(current_checks.get(key, []), current_tracked.get(key, 0))
        baseline = _metric_snapshot(baseline_checks.get(key, []), baseline_tracked.get(key, 0))
        results[key] = {
            "tracked": _metric_change(current.tracked, baseline.tracked),
            "top10": _metric_change(current.top_10, baseline.top_10),
            "top50": _metric_change(current.top_50, baseline.top_50),
            "notVisible": _metric_change(
                current.not_visible,
                baseline.not_visible,
                lower_is_better=True,
            ),
            "averageRank": _metric_change(
                current.average_rank,
                baseline.average_rank,
                lower_is_better=True,
            ),
        }
    return results


def _metric_snapshot(checks: list[RankCheck], tracked: int) -> MetricSnapshot:
    ranks = [int(check.rank) for check in checks if check.found and check.rank is not None]
    return MetricSnapshot(
        tracked=tracked,
        top_10=sum(rank <= 10 for rank in ranks),
        top_50=sum(rank <= 50 for rank in ranks),
        not_visible=sum(not check.found for check in checks),
        average_rank=fmean(ranks) if ranks else None,
    )


def _metric_change(
    current: float | None,
    baseline: float | None,
    *,
    lower_is_better: bool = False,
) -> MetricTrend:
    current_value = current or 0.0
    baseline_value = baseline or 0.0
    if baseline_value == 0:
        percent = 0.0 if current_value == 0 else None
    else:
        delta = current_value - baseline_value
        percent = round(delta / baseline_value * 100, 1)
        if percent == 0:
            percent = 0.0
    if percent is None or percent == 0:
        better = None
    elif lower_is_better:
        better = current_value < baseline_value
    else:
        better = current_value > baseline_value
    return MetricTrend(
        current=round(current_value, 1),
        baseline=round(baseline_value, 1),
        percent=percent,
        better=better,
    )


def _utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _mover_label(item: tuple[int, RankingRow | None]) -> str:
    change, row = item
    if row is None or change == 0:
        return "—"
    return f"{row.target.keyword.keyword} ({change:+d})"


def opportunity_group(check: RankCheck) -> str:
    if not check.found or check.rank is None:
        return "Not currently visible"
    if check.rank <= 10:
        return "Defend (1-10)"
    if check.rank <= 20:
        return "Close wins (11-20)"
    if check.rank <= 50:
        return "Growth opportunities (21-50)"
    if check.rank <= 100:
        return "Weak visibility (51-100)"
    return "Very weak visibility (101-200)"
