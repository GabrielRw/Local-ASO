"""Transparent audience and competition estimates from public search results."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from local_aso_tracker.apple.schemas import AppleSoftwareResult

ESTIMATE_VERSION = "ratings-model-v1"
RESULT_WINDOW = 10
VOLUME_SCALE = 3_000_000
DIFFICULTY_SCALE = 1_000_000
COVERAGE_TARGET = 5
POSITION_WEIGHTS = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70, 0.64, 0.58, 0.52, 0.46)


@dataclass(frozen=True)
class KeywordEstimates:
    """Local scores derived only from ratings attached to Apple search results."""

    volume: int | None
    difficulty: int | None
    sample_size: int


def estimate_keyword(results: Sequence[AppleSoftwareResult]) -> KeywordEstimates:
    """Estimate audience and top-10 competition without claiming search volume."""

    sample = list(results[:RESULT_WINDOW])
    rated = [
        (position, result)
        for position, result in enumerate(sample)
        if (result.user_rating_count or 0) > 0
    ]
    if not rated:
        return KeywordEstimates(volume=None, difficulty=None, sample_size=0)

    rating_logs = [math.log1p(result.user_rating_count or 0) for _, result in rated]
    weights = [POSITION_WEIGHTS[position] for position, _ in rated]
    weight_sum = sum(weights)
    weighted_log = sum(value * weight for value, weight in zip(rating_logs, weights, strict=True))
    mean_log = weighted_log / weight_sum
    coverage = min(1.0, len(rated) / COVERAGE_TARGET)
    volume = round(100 * mean_log / math.log1p(VOLUME_SCALE) * coverage)

    quality_signals = [
        (position, result.average_user_rating / 5)
        for position, result in rated
        if result.average_user_rating is not None
    ]
    quality = (
        sum(value * POSITION_WEIGHTS[position] for position, value in quality_signals)
        / sum(POSITION_WEIGHTS[position] for position, _ in quality_signals)
        if quality_signals
        else 0.0
    )
    strength = 100 * mean_log / math.log1p(DIFFICULTY_SCALE)
    density = 100 * coverage
    difficulty = round(0.65 * strength + 0.25 * density + 0.10 * 100 * quality)
    return KeywordEstimates(
        volume=max(0, min(100, volume)),
        difficulty=max(0, min(100, difficulty)),
        sample_size=len(rated),
    )
