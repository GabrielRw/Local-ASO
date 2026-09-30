"""Spreadsheet-friendly export tests."""

import csv
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from local_aso_tracker.models import RankCheck
from local_aso_tracker.reports.exports import export_latest_csv
from local_aso_tracker.reports.html import generate_html_report
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    list_targets,
)


def test_csv_export_creates_directories_and_utf8_bom(session: Session, tmp_path: Path) -> None:
    add_app(session, "Étoiles", 123)
    add_keyword(session, "thème astral")
    add_storefront(session, "fr", "France")
    target, _ = add_target(session, 123, "thème astral", "fr")
    session.add(
        RankCheck(
            tracking_target_id=target.id,
            checked_at=datetime.now(UTC),
            rank=None,
            found=False,
            result_limit=200,
            response_time_ms=42,
            status="success",
        )
    )
    session.flush()
    output = tmp_path / "nested" / "rankings.csv"
    assert export_latest_csv(session, list_targets(session), output) == 1
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["app"] == "Étoiles"
    assert rows[0]["device"] == "iphone"
    assert rows[0]["rank"] == ">200"

    report = tmp_path / "report.html"
    assert generate_html_report(session, list_targets(session), report) == 1
    report_html = report.read_text(encoding="utf-8")
    assert "All devices" in report_html
    assert "iPadSoftware" in report_html
    assert '"device": "iphone"' in report_html
