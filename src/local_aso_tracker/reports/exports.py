"""CSV and JSON exports of locally stored ranking data."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from local_aso_tracker.models import TrackingTarget
from local_aso_tracker.repositories.data import latest_pairs, successful_checks
from local_aso_tracker.services.analytics import RankingRow, movement


def export_latest_csv(session: Session, targets: list[TrackingTarget], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    pairs = latest_pairs(session, targets)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "app",
                "apple_app_id",
                "keyword",
                "country",
                "device",
                "rank",
                "found",
                "previous_rank",
                "change",
                "checked_at",
            ],
        )
        writer.writeheader()
        for target in targets:
            if target.id not in pairs:
                continue
            latest, previous = pairs[target.id]
            writer.writerow(
                {
                    "app": target.app.name,
                    "apple_app_id": target.app.apple_app_id,
                    "keyword": target.keyword.keyword,
                    "country": target.storefront.country_code,
                    "device": target.device,
                    "rank": latest.rank if latest.rank is not None else f">{latest.result_limit}",
                    "found": latest.found,
                    "previous_rank": previous.rank
                    if previous and previous.rank is not None
                    else "",
                    "change": movement(latest, previous),
                    "checked_at": latest.checked_at.isoformat(),
                }
            )
    return len(pairs)


def export_history_csv(session: Session, targets: list[TrackingTarget], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    target_map = {target.id: target for target in targets}
    checks = successful_checks(session, targets)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "app",
                "apple_app_id",
                "keyword",
                "country",
                "device",
                "rank",
                "found",
                "checked_at",
                "result_limit",
                "total_results_reported",
                "response_time_ms",
                "app_version_returned",
            ],
        )
        writer.writeheader()
        for check in checks:
            target = target_map[check.tracking_target_id]
            writer.writerow(
                {
                    "app": target.app.name,
                    "apple_app_id": target.app.apple_app_id,
                    "keyword": target.keyword.keyword,
                    "country": target.storefront.country_code,
                    "device": target.device,
                    "rank": check.rank if check.rank is not None else f">{check.result_limit}",
                    "found": check.found,
                    "checked_at": check.checked_at.isoformat(),
                    "result_limit": check.result_limit,
                    "total_results_reported": check.total_results_reported,
                    "response_time_ms": check.response_time_ms,
                    "app_version_returned": check.app_version_returned,
                }
            )
    return len(checks)


def export_json(session: Session, targets: list[TrackingTarget], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    pairs = latest_pairs(session, targets)
    target_map = {target.id: target for target in targets}
    history = successful_checks(session, targets)
    payload = {
        "methodology": (
            "One-based position in Apple's public software or iPadSoftware search response; "
            "absence is not an exact rank."
        ),
        "rankings": [
            _ranking_dict(RankingRow(target, latest, previous))
            for target in targets
            if (pair := pairs.get(target.id))
            for latest, previous in [pair]
        ],
        "history": [
            {
                "target_id": check.tracking_target_id,
                "app_id": target_map[check.tracking_target_id].app.apple_app_id,
                "keyword": target_map[check.tracking_target_id].keyword.keyword,
                "country": target_map[check.tracking_target_id].storefront.country_code,
                "device": target_map[check.tracking_target_id].device,
                "rank": check.rank,
                "found": check.found,
                "result_limit": check.result_limit,
                "checked_at": check.checked_at.isoformat(),
            }
            for check in history
        ],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(history)


def _ranking_dict(row: RankingRow) -> dict[str, object]:
    return {
        "target_id": row.target.id,
        "app": row.target.app.name,
        "apple_app_id": row.target.app.apple_app_id,
        "keyword": row.target.keyword.keyword,
        "country": row.target.storefront.country_code,
        "device": row.target.device,
        "rank": row.latest.rank,
        "found": row.latest.found,
        "result_limit": row.latest.result_limit,
        "previous_rank": row.previous.rank if row.previous else None,
        "change": row.change,
        "checked_at": row.latest.checked_at.isoformat(),
    }
