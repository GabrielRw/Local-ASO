"""App Store Connect authentication and metadata request tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from local_aso_tracker.apple.app_store_connect import (
    AppStoreConnectClient,
    AppStoreConnectError,
    connection_status,
)
from local_aso_tracker.config import Settings


def _credentials(tmp_path: Path) -> tuple[Settings, Any]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "AuthKey_TEST.p8"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)
    settings = Settings(
        app_store_connect_issuer_id="issuer-test",
        app_store_connect_key_id="key-test",
        app_store_connect_key_path=str(key_path),
    )
    return settings, private_key.public_key()


def _snapshot_handler(
    *,
    version_state: str = "PREPARE_FOR_SUBMISSION",
    include_existing_localizations: bool = True,
    public_key: Any,
    captured: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        token = request.headers["Authorization"].removeprefix("Bearer ")
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="appstoreconnect-v1",
            issuer="issuer-test",
        )
        assert decoded["exp"] - decoded["iat"] == 20 * 60
        assert jwt.get_unverified_header(token)["kid"] == "key-test"

        path = request.url.path
        if path == "/v1/apps":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "app-1",
                            "type": "apps",
                            "attributes": {
                                "name": "AstroLingo",
                                "bundleId": "com.example.astrolingo",
                                "primaryLocale": "en-US",
                                "sku": "ASTRO",
                            },
                        }
                    ]
                },
            )
        if path == "/v1/apps/app-1/appInfos":
            return httpx.Response(
                200,
                json={"data": [{"id": "info-1", "type": "appInfos", "attributes": {}}]},
            )
        if path == "/v1/apps/app-1/appStoreVersions":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "version-1",
                            "type": "appStoreVersions",
                            "attributes": {
                                "createdDate": "2026-11-01T10:00:00Z",
                                "appStoreState": version_state,
                            },
                        }
                    ]
                },
            )
        if path == "/v1/appInfos/info-1/appInfoLocalizations":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "info-locale-1",
                            "type": "appInfoLocalizations",
                            "attributes": {
                                "locale": "en-US",
                                "name": "Learn Astrology: AstroLingo",
                                "subtitle": "Birth chart lessons",
                                "privacyPolicyUrl": "https://example.com/privacy",
                                "privacyChoicesUrl": "https://example.com/choices",
                                "privacyPolicyText": "We do not collect personal data.",
                            },
                        }
                    ]
                    if include_existing_localizations
                    else []
                },
            )
        if path == "/v1/appStoreVersions/version-1/appStoreVersionLocalizations":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "version-locale-1",
                            "type": "appStoreVersionLocalizations",
                            "attributes": {
                                "locale": "en-US",
                                "description": "Learn astrology.",
                                "keywords": "astrology,zodiac",
                                "promotionalText": "Start today.",
                                "whatsNew": "Improved lessons.",
                                "supportUrl": "https://example.com/support",
                                "marketingUrl": "https://example.com",
                            },
                        }
                    ]
                    if include_existing_localizations
                    else []
                },
            )
        if path == "/v1/appInfoLocalizations":
            assert request.method == "POST"
            return httpx.Response(
                201,
                json={"data": {"id": "info-locale-created", "type": "appInfoLocalizations"}},
            )
        if path == "/v1/appStoreVersionLocalizations":
            assert request.method == "POST"
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": "version-locale-created",
                        "type": "appStoreVersionLocalizations",
                    }
                },
            )
        if path == "/v1/appInfoLocalizations/info-locale-1":
            assert request.method == "PATCH"
            return httpx.Response(
                200,
                json={"data": {"id": "info-locale-1", "type": "appInfoLocalizations"}},
            )
        if path == "/v1/appStoreVersionLocalizations/version-locale-1":
            assert request.method == "PATCH"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "version-locale-1",
                        "type": "appStoreVersionLocalizations",
                    }
                },
            )
        raise AssertionError(
            f"unexpected App Store Connect request: {request.method} {request.url}"
        )

    return httpx.MockTransport(handler)


def test_snapshot_uses_an_ES256_token_and_reads_localizations(tmp_path: Path) -> None:
    settings, public_key = _credentials(tmp_path)
    captured: list[httpx.Request] = []
    with (
        httpx.Client(transport=_snapshot_handler(public_key=public_key, captured=captured)) as http,
        AppStoreConnectClient(settings, client=http) as client,
    ):
        snapshot = client.snapshot(bundle_id="com.example.astrolingo")

    assert snapshot.app.name == "AstroLingo"
    assert snapshot.version_id == "version-1"
    assert snapshot.localizations["en-US"].subtitle == "Birth chart lessons"
    assert snapshot.localizations["en-US"].version_localization_id == "version-locale-1"
    assert len(captured) == 5
    apps_request = captured[0]
    assert apps_request.url.params["filter[bundleId]"] == "com.example.astrolingo"


def test_push_updates_existing_app_info_and_version_localization(tmp_path: Path) -> None:
    settings, public_key = _credentials(tmp_path)
    captured: list[httpx.Request] = []
    fields = {
        "name": "Aprender astrología: AstroLingo",
        "subtitle": "Lecciones de carta natal",
        "keywords": "horóscopo,zodiaco",
        "description": "Aprende astrología.",
        "promotionalText": "Empieza hoy.",
        "whatsNew": "Lecciones mejoradas.",
    }
    with (
        httpx.Client(transport=_snapshot_handler(public_key=public_key, captured=captured)) as http,
        AppStoreConnectClient(settings, client=http) as client,
    ):
        result = client.push_localization(
            bundle_id="com.example.astrolingo",
            target_locale="en-US",
            fields=fields,
        )

    patches = [request for request in captured if request.method == "PATCH"]
    assert len(patches) == 2
    app_info_body = json.loads(patches[0].content)
    version_body = json.loads(patches[1].content)
    assert app_info_body["data"]["attributes"] == {
        "name": fields["name"],
        "subtitle": fields["subtitle"],
    }
    assert version_body["data"]["attributes"] == {
        "description": fields["description"],
        "keywords": fields["keywords"],
        "promotionalText": fields["promotionalText"],
        "whatsNew": fields["whatsNew"],
    }
    assert result["before"]["name"] == "Learn Astrology: AstroLingo"
    assert result["versionState"] == "PREPARE_FOR_SUBMISSION"


def test_push_creates_new_locale_with_source_urls_preserved(tmp_path: Path) -> None:
    settings, public_key = _credentials(tmp_path)
    captured: list[httpx.Request] = []
    with (
        httpx.Client(
            transport=_snapshot_handler(
                include_existing_localizations=False,
                public_key=public_key,
                captured=captured,
            )
        ) as http,
        AppStoreConnectClient(settings, client=http) as client,
    ):
        result = client.push_localization(
            bundle_id="com.example.astrolingo",
            target_locale="fr-FR",
            fields={
                "name": "AstroLingo",
                "subtitle": "Leçons de thème natal",
                "keywords": "astrologie,zodiaque",
                "description": "Apprenez l'astrologie.",
                "promotionalText": "Commencez aujourd'hui.",
                "whatsNew": "Leçons améliorées.",
            },
            preserved_fields={
                "privacyPolicyUrl": "https://example.com/privacy",
                "privacyChoicesUrl": "https://example.com/choices",
                "privacyPolicyText": "We do not collect personal data.",
                "supportUrl": "https://example.com/support",
                "marketingUrl": "https://example.com",
            },
        )

    posts = [request for request in captured if request.method == "POST"]
    assert len(posts) == 2
    app_info_body = json.loads(posts[0].content)
    version_body = json.loads(posts[1].content)
    assert app_info_body["data"]["attributes"]["privacyPolicyUrl"] == (
        "https://example.com/privacy"
    )
    assert app_info_body["data"]["attributes"]["privacyPolicyText"] == (
        "We do not collect personal data."
    )
    assert version_body["data"]["attributes"]["supportUrl"] == "https://example.com/support"
    assert version_body["data"]["attributes"]["marketingUrl"] == "https://example.com"
    assert result["appInfoLocalizationId"] == "info-locale-created"
    assert result["versionLocalizationId"] == "version-locale-created"


def test_push_rejects_non_editable_version_before_writing(tmp_path: Path) -> None:
    settings, public_key = _credentials(tmp_path)
    captured: list[httpx.Request] = []
    with (
        httpx.Client(
            transport=_snapshot_handler(
                version_state="READY_FOR_SALE",
                public_key=public_key,
                captured=captured,
            )
        ) as http,
        AppStoreConnectClient(settings, client=http) as client,
        pytest.raises(AppStoreConnectError, match="not editable"),
    ):
        client.push_localization(
            bundle_id="com.example.astrolingo",
            target_locale="en-US",
            fields={"name": "AstroLingo"},
        )

    assert not [request for request in captured if request.method in {"PATCH", "POST"}]


def test_connection_is_not_ready_when_private_key_permissions_are_unsafe(
    tmp_path: Path,
) -> None:
    settings, _ = _credentials(tmp_path)
    Path(settings.app_store_connect_key_path).chmod(0o644)

    status = connection_status(settings)

    assert status["configured"] is True
    assert status["keyExists"] is True
    assert status["keyModeSafe"] is False
    assert status["ready"] is False


def test_connection_reports_only_the_apple_error_detail(tmp_path: Path) -> None:
    settings, _ = _credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/apps"
        return httpx.Response(
            403,
            json={
                "errors": [
                    {
                        "status": "403",
                        "code": "FORBIDDEN_ERROR",
                        "title": "The API key is not authorized",
                        "detail": "This API key cannot access the requested resource.",
                    }
                ]
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        AppStoreConnectClient(settings, client=http) as client,
        pytest.raises(AppStoreConnectError, match="cannot access"),
    ):
        client.test()


def _client(settings: Settings, handler) -> AppStoreConnectClient:  # type: ignore[no-untyped-def]
    client = AppStoreConnectClient(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client._sleep = lambda _seconds: None  # type: ignore[method-assign]
    return client


def test_collections_follow_pagination(tmp_path: Path) -> None:
    settings, _ = _credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "2":
            return httpx.Response(200, json={"data": [{"id": "b"}], "links": {}})
        return httpx.Response(
            200,
            json={
                "data": [{"id": "a"}],
                "links": {"next": "https://api.appstoreconnect.apple.com/v1/things?cursor=2"},
            },
        )

    assert [item["id"] for item in _client(settings, handler)._get_all("/things")] == ["a", "b"]


def test_rate_limits_are_retried_with_retry_after(tmp_path: Path) -> None:
    settings, _ = _credentials(tmp_path)
    calls: list[int] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"errors": []})
        return httpx.Response(200, json={"data": []})

    client = _client(settings, handler)
    client._sleep = waits.append  # type: ignore[method-assign]
    assert client._request("GET", "/apps") == {"data": []}
    assert len(calls) == 3
    assert waits == [7.0, 7.0]


def test_empty_delete_responses_are_ok_and_versions_are_selectable(tmp_path: Path) -> None:
    settings, _ = _credentials(tmp_path)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(204)

    client = _client(settings, handler)
    assert client._request("DELETE", "/things/1") == {}
    client._request("GET", "/appPricePoints/x/equalizations", version="v3")
    assert seen[-1].startswith("https://api.appstoreconnect.apple.com/v3/")
    with pytest.raises(AppStoreConnectError, match="non-App Store Connect URL"):
        client._request("GET", "https://example.com/steal")


def test_snapshot_prefers_the_editable_version_and_app_info() -> None:
    from local_aso_tracker.apple.app_store_connect import _pick_app_info, _pick_version

    versions = [
        {
            "id": "live",
            "attributes": {"appStoreState": "READY_FOR_SALE", "createdDate": "2026-11-10"},
        },
        {
            "id": "next",
            "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION", "createdDate": "2026-11-01"},
        },
    ]
    assert _pick_version(versions)["id"] == "next"
    assert _pick_version(versions[:1])["id"] == "live"
    infos = [
        {"id": "live-info", "attributes": {"state": "READY_FOR_DISTRIBUTION"}},
        {"id": "next-info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}},
    ]
    assert _pick_app_info(infos)["id"] == "next-info"
