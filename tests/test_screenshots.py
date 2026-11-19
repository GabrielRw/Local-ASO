"""Screenshot studio backend: imports, captions, AI drafts (mocked), renders, routes."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from threading import Thread

import httpx
import pytest

from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.repositories.data import add_app, add_storefront
from local_aso_tracker.services import screenshots
from local_aso_tracker.utils.images import image_info
from local_aso_tracker.web.server import DashboardHandler, LocalDashboardServer

APP = 6756268723


def png(width: int, height: int) -> bytes:
    """A real (tiny-payload) PNG with the given header size."""

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    run_migrations()
    with session_scope() as session:
        add_app(session, "Spiritual Couple", APP)
        for code in ("us", "fr", "de"):
            add_storefront(session, code)
    return tmp_path / "data"


def test_image_header_reader() -> None:
    assert image_info(png(1290, 2796)) == ("png", 1290, 2796)
    jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10"
        + b"JFIF\x00"
        + b"\x00" * 9
        + b"\xff\xc0\x00\x11\x08"
        + struct.pack(">HH", 2796, 1290)
        + b"\x00" * 12
    )
    assert image_info(jpeg) == ("jpeg", 1290, 2796)
    with pytest.raises(ValueError):
        image_info(b"GIF89a....")


def test_import_order_and_delete(studio: Path) -> None:
    payload = screenshots.add_source(APP, png(1290, 2796), original_name="home.png")
    payload = screenshots.add_source(APP, png(1290, 2796), original_name="dreams.png")
    sources = payload["sources"]
    assert [item["name"] for item in sources] == ["home.png", "dreams.png"]  # type: ignore[index]
    stored = list((studio / "screenshots").rglob("*.png"))
    assert len(stored) == 2 and all(path.is_relative_to(studio) for path in stored)
    first, second = (item["id"] for item in sources)  # type: ignore[index]
    payload = screenshots.reorder_sources(APP, [second, first])
    assert [item["name"] for item in payload["sources"]] == ["dreams.png", "home.png"]  # type: ignore[index]
    payload = screenshots.delete_source(APP, second)
    assert [(item["name"], item["position"]) for item in payload["sources"]] == [("home.png", 1)]  # type: ignore[index]
    assert len(list((studio / "screenshots").rglob("*.png"))) == 1
    with pytest.raises(ValueError, match="too small"):
        screenshots.add_source(APP, png(100, 100))


def test_locales_follow_active_storefronts(studio: Path) -> None:
    payload = screenshots.studio_payload(APP)
    locales = {item["locale"]: item for item in payload["locales"]}  # type: ignore[union-attr]
    assert set(locales) == {"en-US", "fr-FR", "de-DE"}
    assert locales["en-US"]["isMain"] is True
    assert payload["devices"]["iphone"]["width"] == 1320  # type: ignore[index]


def test_ai_drafts_then_translations_keep_user_edits(
    studio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = screenshots.add_source(APP, png(1290, 2796))
    source_id = payload["sources"][0]["id"]  # type: ignore[index]
    screenshots.add_source(APP, png(1290, 2796))
    monkeypatch.setattr(
        screenshots,
        "generate_screenshot_captions",
        lambda **_kw: (
            "claude",
            {1: ("Feel each other", "Log shared moments"), 2: ("Dream together", "")},
        ),
    )
    payload = screenshots.draft_captions(APP, {"name": "Spiritual Couple"})
    assert payload["sources"][0]["captions"]["en-US"]["origin"] == "ai"  # type: ignore[index]

    screenshots.save_caption(APP, source_id, locale="fr-FR", headline="Mon titre", subline="")
    asked: dict[str, object] = {}

    def fake_translate(**kwargs):  # type: ignore[no-untyped-def]
        asked.update(kwargs)
        return "claude", {
            "fr-FR": {1: ("Ressentez-vous", ""), 2: ("Rêvez ensemble", "")},
            "de-DE": {1: ("Fühlt einander", ""), 2: ("Träumt zusammen", "")},
        }

    monkeypatch.setattr(screenshots, "translate_screenshot_captions", fake_translate)
    payload = screenshots.translate_captions(APP, ["fr-FR", "de-DE", "en-US"])
    assert asked["targets"] == {"fr-FR": "French", "de-DE": "German"}
    first, second = payload["sources"]  # type: ignore[misc]
    assert first["captions"]["fr-FR"]["headline"] == "Mon titre"  # user edit kept
    assert second["captions"]["fr-FR"]["headline"] == "Rêvez ensemble"
    assert first["captions"]["de-DE"]["headline"] == "Fühlt einander"


def test_renders_must_match_app_store_sizes(studio: Path) -> None:
    screenshots.add_source(APP, png(1290, 2796))
    with pytest.raises(ValueError, match="1320x2868"):
        screenshots.save_render(
            APP, locale="fr-FR", device="iphone", position=1, data=png(1290, 2796)
        )
    with pytest.raises(ValueError, match="no screenshot at that position"):
        screenshots.save_render(
            APP, locale="fr-FR", device="iphone", position=2, data=png(1320, 2868)
        )
    saved = screenshots.save_render(
        APP, locale="fr-FR", device="iphone", position=1, data=png(1320, 2868)
    )
    path, kind = screenshots.file_for("render", int(saved["id"]))  # type: ignore[arg-type]
    assert kind == "image/png" and path.name == "01.png" and "fr-FR" in path.parts


def test_binary_upload_route_and_origin_rules(studio: Path) -> None:
    server = LocalDashboardServer(("127.0.0.1", 0), DashboardHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base, trust_env=False) as client:
            ok = client.post(
                f"/api/screenshots/sources?appId={APP}&name=home.png",
                content=png(1290, 2796),
                headers={"Content-Type": "image/png", "Origin": base},
            )
            assert ok.status_code == 200, ok.text
            source_url = ok.json()["sources"][0]["url"]
            preview = client.get(source_url)
            assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
            cross = client.post(
                f"/api/screenshots/sources?appId={APP}",
                content=png(1290, 2796),
                headers={"Content-Type": "image/png", "Origin": "https://evil.example"},
            )
            assert cross.status_code == 403
            wrong_type = client.post(
                f"/api/screenshots/sources?appId={APP}",
                content=b"x",
                headers={"Content-Type": "text/plain"},
            )
            assert wrong_type.status_code == 403
            # Images are only accepted on the upload routes.
            assert (
                client.post(
                    "/api/onboarding/complete",
                    content=png(10, 10),
                    headers={"Content-Type": "image/png"},
                ).status_code
                == 403
            )
    finally:
        server.shutdown()
        server.server_close()


def _asc_settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from local_aso_tracker.config import Settings

    key_path = tmp_path / "AuthKey_TEST.p8"
    key_path.write_bytes(
        ec.generate_private_key(ec.SECP256R1()).private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)
    return Settings(
        app_store_connect_issuer_id="issuer-test",
        app_store_connect_key_id="key-test",
        app_store_connect_key_path=str(key_path),
    )


def test_push_replaces_screenshot_sets_with_apple_upload_flow(
    studio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json

    from local_aso_tracker.apple.app_store_connect import AppStoreConnectClient
    from local_aso_tracker.models import App

    with session_scope() as session:
        session.query(App).filter_by(apple_app_id=APP).one().bundle_id = "com.example.couple"
    screenshots.add_source(APP, png(1290, 2796))
    screenshots.add_source(APP, png(1290, 2796))
    for position in (1, 2):
        screenshots.save_render(
            APP, locale="fr-FR", device="iphone", position=position, data=png(1320, 2868)
        )
    screenshots.save_render(APP, locale="de-DE", device="iphone", position=1, data=png(1320, 2868))

    calls: list[tuple[str, str]] = []
    uploads: list[bytes] = []
    reserved = iter(["new-1", "new-2", "new-3"])

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((request.method, path))
        if request.url.host.endswith("blobstore.apple.com"):
            uploads.append(request.content)
            return httpx.Response(200)
        if path == "/v1/apps":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "app",
                            "attributes": {
                                "bundleId": "com.example.couple",
                                "primaryLocale": "en-US",
                            },
                        }
                    ]
                },
            )
        if path == "/v1/apps/app/appInfos":
            return httpx.Response(
                200,
                json={"data": [{"id": "info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}]},
            )
        if path == "/v1/apps/app/appStoreVersions":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "ver",
                            "attributes": {
                                "appStoreState": "PREPARE_FOR_SUBMISSION",
                                "createdDate": "2026-11-01",
                            },
                        }
                    ]
                },
            )
        if path == "/v1/appInfos/info/appInfoLocalizations":
            return httpx.Response(
                200, json={"data": [{"id": "i-fr", "attributes": {"locale": "fr-FR"}}]}
            )
        if path == "/v1/appStoreVersions/ver/appStoreVersionLocalizations":
            # Only French exists in App Store Connect; German must fail cleanly.
            return httpx.Response(
                200, json={"data": [{"id": "v-fr", "attributes": {"locale": "fr-FR"}}]}
            )
        if path == "/v1/appStoreVersionLocalizations/v-fr/appScreenshotSets":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "set", "attributes": {"screenshotDisplayType": "APP_IPHONE_67"}}
                    ]
                },
            )
        if path == "/v1/appScreenshotSets/set/appScreenshots":
            return httpx.Response(200, json={"data": [{"id": "old-1"}]})
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST" and path == "/v1/appScreenshots":
            body = _json.loads(request.content)
            size = body["data"]["attributes"]["fileSize"]
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": next(reserved),
                        "attributes": {
                            "uploadOperations": [
                                {
                                    "method": "PUT",
                                    "url": "https://store-1.blobstore.apple.com/u",
                                    "offset": 0,
                                    "length": size,
                                    "requestHeaders": [
                                        {"name": "Content-Type", "value": "image/png"}
                                    ],
                                }
                            ]
                        },
                    }
                },
            )
        if request.method == "PATCH":
            assert _json.loads(request.content)["data"]["attributes"]["uploaded"] is True
            return httpx.Response(200, json={"data": {}})
        if request.method == "GET" and path.startswith("/v1/appScreenshots/"):
            return httpx.Response(
                200, json={"data": {"attributes": {"assetDeliveryState": {"state": "COMPLETE"}}}}
            )
        return httpx.Response(404, json={"errors": [{"detail": f"unexpected {path}"}]})

    client = AppStoreConnectClient(
        _asc_settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client._sleep = lambda _seconds: None  # type: ignore[method-assign]
    result = screenshots.push_to_app_store_connect(
        APP, locales=["fr-FR", "de-DE"], devices=["iphone"], client=client
    )

    by_locale = {item["locale"]: item for item in result["results"]}  # type: ignore[union-attr]
    assert by_locale["fr-FR"] == {
        "locale": "fr-FR",
        "device": "iphone",
        "uploaded": 2,
        "error": None,
    }
    assert "push its listing text first" in str(by_locale["de-DE"]["error"])
    assert ("DELETE", "/v1/appScreenshots/old-1") in calls
    assert len(uploads) == 2
    payload = screenshots.studio_payload(APP)
    statuses = sorted((event["locale"], event["status"]) for event in payload["pushEvents"])  # type: ignore[union-attr]
    assert statuses == [("de-DE", "failed"), ("fr-FR", "success")]


def test_push_refuses_a_version_that_is_not_editable(studio: Path, tmp_path: Path) -> None:
    from local_aso_tracker.apple.app_store_connect import AppStoreConnectClient
    from local_aso_tracker.models import App

    with session_scope() as session:
        session.query(App).filter_by(apple_app_id=APP).one().bundle_id = "com.example.couple"
    screenshots.add_source(APP, png(1290, 2796))
    screenshots.save_render(APP, locale="fr-FR", device="iphone", position=1, data=png(1320, 2868))
    writes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            writes.append(request.url.path)
        path = request.url.path
        if path == "/v1/apps":
            return httpx.Response(200, json={"data": [{"id": "app", "attributes": {}}]})
        if path.endswith("/appInfos"):
            return httpx.Response(200, json={"data": [{"id": "info", "attributes": {}}]})
        if path.endswith("/appStoreVersions"):
            return httpx.Response(
                200,
                json={"data": [{"id": "ver", "attributes": {"appStoreState": "READY_FOR_SALE"}}]},
            )
        return httpx.Response(200, json={"data": []})

    client = AppStoreConnectClient(
        _asc_settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ValueError, match="READY_FOR_SALE"):
        screenshots.push_to_app_store_connect(
            APP, locales=["fr-FR"], devices=["iphone"], client=client
        )
    assert writes == []


def test_fastlane_export_includes_rendered_screenshots(studio: Path) -> None:
    from local_aso_tracker.repositories.data import save_listing_metadata
    from local_aso_tracker.web.server import DashboardService

    with session_scope() as session:
        save_listing_metadata(
            session,
            APP,
            "us",
            name="Spiritual Couple",
            subtitle="",
            keyword_field="",
            channel_goal="aso_seo_aeo",
            brand_term="Spiritual Couple",
        )
    screenshots.add_source(APP, png(1290, 2796))
    screenshots.save_render(APP, locale="fr-FR", device="iphone", position=1, data=png(1320, 2868))
    screenshots.save_render(APP, locale="fr-FR", device="ipad", position=1, data=png(2064, 2752))
    result = DashboardService().export_fastlane({"appId": APP})
    root = Path(str(result["path"])).parent
    shots = sorted(
        path.relative_to(root).as_posix() for path in (root / "screenshots").rglob("*.png")
    )
    assert shots == ["screenshots/fr-FR/01_ipad.png", "screenshots/fr-FR/01_iphone.png"]
