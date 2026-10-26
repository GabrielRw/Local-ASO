"""Local MCP write-action tests with Apple requests mocked."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from local_aso_tracker.apple.listing import AppleListing
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import list_targets, seed_catalog
from local_aso_tracker.services import mcp_actions


@pytest.fixture
def action_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        seed_catalog(session)


def test_add_keywords_creates_cross_product_without_checking(action_database: None) -> None:
    result = mcp_actions.add_keywords(
        6771773264,
        ["keto tracker", "KETO TRACKER", "keto diet"],
        ["us", "fr"],
        devices=["iphone", "ipad"],
        check_now=False,
    )

    assert result["keywords"] == ["keto tracker", "keto diet"]
    assert result["targetsCreated"] == 8
    assert result["check"] is None
    with session_scope() as session:
        targets = list_targets(session, keyword="keto tracker", active_only=True)
    assert {(target.storefront.country_code, target.device) for target in targets} == {
        ("us", "iphone"),
        ("us", "ipad"),
        ("fr", "iphone"),
        ("fr", "ipad"),
    }


def test_add_keywords_can_run_initial_checks(
    action_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_targets: list[int] = []

    def fake_run_checks(session, targets, settings):  # type: ignore[no-untyped-def]
        checked_targets.extend(target.id for target in targets)
        return SimpleNamespace(checks=[object()] * len(targets), searches=2, failures=0)

    monkeypatch.setattr(mcp_actions, "run_checks", fake_run_checks)
    result = mcp_actions.add_keywords(
        6771773264,
        ["keto tracker"],
        ["us", "fr"],
    )

    assert result["check"] == {"checks": 2, "searches": 2, "failures": 0}
    assert len(checked_targets) == 2


def test_stop_tracking_keywords_preserves_history_rows(action_database: None) -> None:
    mcp_actions.add_keywords(
        6771773264,
        ["keto tracker"],
        ["us", "fr"],
        check_now=False,
    )

    result = mcp_actions.stop_tracking_keywords(
        6771773264,
        ["KETO TRACKER"],
        countries=["fr"],
    )

    assert result["deactivated"] == 1
    with session_scope() as session:
        active = list_targets(session, keyword="keto tracker", active_only=True)
        all_targets = list_targets(session, keyword="keto tracker")
    assert len(active) == 1
    assert active[0].storefront.country_code == "us"
    assert len(all_targets) == 2


def test_add_app_uses_public_listing_and_restores_existing_app(
    action_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = AppleListing.model_validate(
        {
            "trackId": 123456789,
            "trackName": "MCP app",
            "bundleId": "com.example.mcp",
            "artworkUrl100": "https://is1-ssl.mzstatic.com/mcp.png",
        }
    )
    monkeypatch.setattr(mcp_actions, "lookup_listing", lambda *_args, **_kwargs: listing)

    first = mcp_actions.add_app(123456789, "us")
    second = mcp_actions.add_app(123456789, "us")

    assert first["created"] is True
    assert second["created"] is False
    assert second["restored"] is False
