"""Ranking movement and summary calculations."""

from __future__ import annotations

from dataclasses import dataclass
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
