"""fastlane metadata export, export-folder containment, and the POST origin check."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

import httpx
import pytest

from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import add_app
from local_aso_tracker.repositories.listing_localizations import (
    approve_localization_draft,
    upsert_localization_draft,
)
from local_aso_tracker.web.server import DashboardHandler, DashboardService, LocalDashboardServer

SOURCE = {
    "name": "Spiritual Couple",
    "subtitle": "Psychic Connection app",
    "keywords": "couples,telepathy",
    "description": "Notice the moments you think of each other.",
    "promotionalText": "",
    "whatsNew": "",
    "supportUrl": "https://example.com/support",
    "privacyPolicyUrl": "https://example.com/privacy",
}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Spiritual Couple", 6756268723, "com.example.couple")
        for locale, status in (("fr-FR", "approve"), ("de-DE", "draft")):
            draft = upsert_localization_draft(
                session,
                app_id=app.id,
                source_country="us",
                source_locale="en-US",
                target_locale=locale,
                target_countries=[locale[-2:].lower()],
                language="French" if locale == "fr-FR" else "German",
                provider="claude",
                source_fields=SOURCE,
                fields={
                    "name": "Couple Spirituel" if locale == "fr-FR" else "Spirituelles Paar",
                    "subtitle": "Connexion psychique",
                    "keywords": "couple,télépathie",
                    "description": "Remarquez les moments partagés.",
                    "promotionalText": "",
                    "whatsNew": "",
                },
                validation={"errors": [], "warnings": []},
                iteration_count=1,
            )
            if status == "approve":
                session.flush()
                approve_localization_draft(session, draft)
        return app.id


def test_fastlane_export_writes_main_and_approved_locales(workspace: int) -> None:
    result = DashboardService().export_fastlane({"appId": 6756268723})
    metadata = Path(str(result["path"]))
    assert result["locales"] == ["en-US", "fr-FR"]
    assert result["skipped"] == [{"locale": "de-DE", "reason": "status is needs_review"}]
    assert metadata.name == "metadata"
    assert "com.example.couple" in metadata.parts
    assert (metadata / "en-US" / "name.txt").read_text(encoding="utf-8") == "Spiritual Couple\n"
    assert (metadata / "fr-FR" / "keywords.txt").read_text(
        encoding="utf-8"
    ) == "couple,télépathie\n"
    assert (metadata / "fr-FR" / "support_url.txt").exists()
    assert (metadata / "fr-FR" / "privacy_url.txt").exists()
    # Empty fields are not written, so `deliver` leaves them alone.
    assert not (metadata / "en-US" / "promotional_text.txt").exists()

    everything = DashboardService().export_fastlane(
        {"appId": 6756268723, "includeUnapproved": True}
    )
    assert everything["locales"] == ["de-DE", "en-US", "fr-FR"]


def test_reveal_is_limited_to_the_exports_folder(workspace: int, tmp_path: Path) -> None:
    service = DashboardService()
    exported = service.export_fastlane({"appId": 6756268723})
    service.reveal_export({"path": exported["path"]})  # inside: allowed (no-op off macOS)
    for outside in (str(tmp_path), "/etc", f"{exported['path']}/../../../../.."):
        with pytest.raises(ValueError, match="only exported folders"):
            service.reveal_export({"path": outside})


@pytest.fixture
def live_server(workspace: int):  # type: ignore[no-untyped-def]
    server = LocalDashboardServer(("127.0.0.1", 0), DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_posts_from_other_web_pages_are_rejected(live_server: str) -> None:
    with httpx.Client(base_url=live_server, trust_env=False) as client:
        body = {"appId": 6756268723}
        same_origin = client.post(
            "/api/exports/fastlane", json=body, headers={"Origin": live_server}
        )
        assert same_origin.status_code == 200
        cross = client.post(
            "/api/exports/fastlane", json=body, headers={"Origin": "https://evil.example"}
        )
        assert cross.status_code == 403
        form = client.post(
            "/api/onboarding/complete",
            content='{"x": 1}',
            headers={"Content-Type": "text/plain", "Origin": live_server},
        )
        assert form.status_code == 403
        rebinding = client.post(
            "/api/onboarding/complete", json={}, headers={"Host": "attacker.example"}
        )
        assert rebinding.status_code == 403
        # Non-browser clients (CLI scripts, tests) send no Origin and are allowed.
        assert client.post("/api/onboarding/complete", json={}).status_code == 200


def test_export_falls_back_to_the_listing_saved_in_optimize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from local_aso_tracker.repositories.data import add_storefront, save_listing_metadata

    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    run_migrations()
    with session_scope() as session:
        add_app(session, "Spiritual Couple", 6756268723)
        for country in ("fr", "us"):
            add_storefront(session, country)
            save_listing_metadata(
                session,
                6756268723,
                country,
                name="Spiritual Couple : I Feel You",
                subtitle="Psychic Connection app",
                keyword_field="energy relationship,intimacy",
                channel_goal="aso_seo_aeo",
                brand_term="Spiritual Couple",
            )
    result = DashboardService().export_fastlane({"appId": 6756268723})
    metadata = Path(str(result["path"]))
    # No main storefront picked in the studio: the US listing is used.
    assert result["locales"] == ["en-US"]
    assert (metadata / "en-US" / "subtitle.txt").read_text(
        encoding="utf-8"
    ) == "Psychic Connection app\n"
