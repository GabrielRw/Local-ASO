"""Minimal local App Store Connect API client for listing metadata."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import jwt

from local_aso_tracker.config import Settings

APP_STORE_CONNECT_ROOT = "https://api.appstoreconnect.apple.com"
APP_STORE_CONNECT_BASE_URL = f"{APP_STORE_CONNECT_ROOT}/v1"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 30.0
# App info states that are not the live record (the editable copy for the next version).
_LIVE_APP_INFO_STATES = {"READY_FOR_DISTRIBUTION", "REPLACED_WITH_NEW_INFO"}
EDITABLE_VERSION_STATES = {
    "PREPARE_FOR_SUBMISSION",
    "INVALID_BINARY",
    "REJECTED",
    "METADATA_REJECTED",
    "DEVELOPER_REJECTED",
}


class AppStoreConnectError(RuntimeError):
    """App Store Connect could not complete a local authenticated request."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class AppStoreConnectApp:
    id: str
    name: str
    bundle_id: str
    primary_locale: str
    sku: str | None


@dataclass(frozen=True)
class AppStoreConnectLocalization:
    app_info_id: str
    version_id: str
    version_state: str
    locale: str
    app_info_localization_id: str | None
    version_localization_id: str | None
    name: str
    subtitle: str
    description: str
    keywords: str
    promotional_text: str
    whats_new: str
    support_url: str
    marketing_url: str
    privacy_policy_url: str
    privacy_choices_url: str
    privacy_policy_text: str


@dataclass(frozen=True)
class AppStoreConnectSnapshot:
    app: AppStoreConnectApp
    app_info_id: str
    version_id: str
    version_state: str
    localizations: dict[str, AppStoreConnectLocalization]

    def source(self, locale: str) -> AppStoreConnectLocalization | None:
        return self.localizations.get(locale) or self.localizations.get(self.app.primary_locale)


def connection_status(settings: Settings) -> dict[str, object]:
    key_path = Path(settings.app_store_connect_key_path).expanduser()
    configured = bool(
        settings.app_store_connect_issuer_id
        and settings.app_store_connect_key_id
        and settings.app_store_connect_key_path
    )
    key_exists = key_path.is_file() if settings.app_store_connect_key_path else False
    mode_safe = _key_mode_is_safe(key_path) if key_exists else False
    return {
        "configured": configured,
        "ready": configured and key_exists and mode_safe,
        "issuerId": settings.app_store_connect_issuer_id,
        "keyId": settings.app_store_connect_key_id,
        "keyPath": settings.app_store_connect_key_path,
        "keyExists": key_exists,
        "keyModeSafe": mode_safe,
    }


class AppStoreConnectClient:
    """Synchronous client used only by the local dashboard backend."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self._external_client = client
        self._client = client or httpx.Client(
            timeout=settings.request_timeout,
            headers={"Accept": "application/json"},
        )
        self._owns_client = client is None

    def __enter__(self) -> AppStoreConnectClient:
        return self

    def __exit__(self, *_args: object) -> None:
        if self._owns_client:
            self._client.close()

    def test(self) -> dict[str, object]:
        payload = self._request("GET", "/apps", params={"limit": 1})
        return {"connected": True, "appsVisible": len(payload.get("data", []))}

    def snapshot(
        self,
        *,
        bundle_id: str,
    ) -> AppStoreConnectSnapshot:
        apps = self._request(
            "GET",
            "/apps",
            params={
                "filter[bundleId]": bundle_id,
                "fields[apps]": "name,bundleId,primaryLocale,sku",
                "limit": 10,
            },
        ).get("data", [])
        if not apps:
            raise AppStoreConnectError("the App Store Connect API key cannot access this bundle ID")
        raw_app = apps[0]
        attributes = raw_app.get("attributes", {})
        app = AppStoreConnectApp(
            id=str(raw_app["id"]),
            name=str(attributes.get("name") or ""),
            bundle_id=str(attributes.get("bundleId") or bundle_id),
            primary_locale=str(attributes.get("primaryLocale") or ""),
            sku=str(attributes["sku"]) if attributes.get("sku") else None,
        )
        app_infos = self._request(
            "GET",
            f"/apps/{app.id}/appInfos",
            params={"limit": 20, "fields[appInfos]": "state"},
        ).get("data", [])
        if not app_infos:
            raise AppStoreConnectError("no App Info record is available for this app")
        app_info_id = str(_pick_app_info(app_infos)["id"])
        versions = self._request(
            "GET",
            f"/apps/{app.id}/appStoreVersions",
            params={
                "filter[platform]": "IOS",
                "limit": 50,
                "fields[appStoreVersions]": "versionString,appStoreState,createdDate,platform",
            },
        ).get("data", [])
        if not versions:
            raise AppStoreConnectError("no iOS App Store version is available")
        raw_version = _pick_version(versions)
        version_id = str(raw_version["id"])
        version_state = str(raw_version.get("attributes", {}).get("appStoreState") or "")
        app_info_localizations = self._get_all(
            f"/appInfos/{app_info_id}/appInfoLocalizations",
            params={
                "limit": 200,
                "fields[appInfoLocalizations]": (
                    "locale,name,subtitle,privacyPolicyUrl,privacyChoicesUrl,privacyPolicyText"
                ),
            },
        )
        version_localizations = self._get_all(
            f"/appStoreVersions/{version_id}/appStoreVersionLocalizations",
            params={
                "limit": 200,
                "fields[appStoreVersionLocalizations]": (
                    "locale,description,keywords,promotionalText,supportUrl,marketingUrl,whatsNew"
                ),
            },
        )
        app_info_by_locale = {
            str(item.get("attributes", {}).get("locale") or ""): item
            for item in app_info_localizations
        }
        version_by_locale = {
            str(item.get("attributes", {}).get("locale") or ""): item
            for item in version_localizations
        }
        localizations: dict[str, AppStoreConnectLocalization] = {}
        for locale in sorted(set(app_info_by_locale) | set(version_by_locale)):
            if not locale:
                continue
            info = app_info_by_locale.get(locale, {})
            version = version_by_locale.get(locale, {})
            info_attributes = info.get("attributes", {})
            version_attributes = version.get("attributes", {})
            localizations[locale] = AppStoreConnectLocalization(
                app_info_id=app_info_id,
                version_id=version_id,
                version_state=version_state,
                locale=locale,
                app_info_localization_id=(str(info["id"]) if info.get("id") is not None else None),
                version_localization_id=(
                    str(version["id"]) if version.get("id") is not None else None
                ),
                name=str(info_attributes.get("name") or ""),
                subtitle=str(info_attributes.get("subtitle") or ""),
                description=str(version_attributes.get("description") or ""),
                keywords=str(version_attributes.get("keywords") or ""),
                promotional_text=str(version_attributes.get("promotionalText") or ""),
                whats_new=str(version_attributes.get("whatsNew") or ""),
                support_url=str(version_attributes.get("supportUrl") or ""),
                marketing_url=str(version_attributes.get("marketingUrl") or ""),
                privacy_policy_url=str(info_attributes.get("privacyPolicyUrl") or ""),
                privacy_choices_url=str(info_attributes.get("privacyChoicesUrl") or ""),
                privacy_policy_text=str(info_attributes.get("privacyPolicyText") or ""),
            )
        return AppStoreConnectSnapshot(
            app=app,
            app_info_id=app_info_id,
            version_id=version_id,
            version_state=version_state,
            localizations=localizations,
        )

    def push_localization(
        self,
        *,
        bundle_id: str,
        target_locale: str,
        fields: dict[str, str],
        preserved_fields: dict[str, str] | None = None,
    ) -> dict[str, object]:
        snapshot = self.snapshot(bundle_id=bundle_id)
        if snapshot.version_state not in EDITABLE_VERSION_STATES:
            raise AppStoreConnectError(
                "App Store metadata is not editable; promotional text may be updated "
                "only after the version enters an editable state"
            )
        existing = snapshot.localizations.get(target_locale)
        before = (
            {
                key: getattr(existing, key)
                for key in (
                    "name",
                    "subtitle",
                    "description",
                    "keywords",
                    "promotional_text",
                    "whats_new",
                )
            }
            if existing is not None
            else {}
        )
        app_info_id = existing.app_info_localization_id if existing else None
        version_localization_id = existing.version_localization_id if existing else None
        app_info_attributes = {key: fields[key] for key in ("name", "subtitle") if key in fields}
        version_attributes = {
            key: fields[key]
            for key in ("description", "keywords", "promotionalText", "whatsNew")
            if key in fields
        }
        preserved = {
            key: str(value)
            for key, value in (preserved_fields or {}).items()
            if key
            in {
                "privacyPolicyUrl",
                "privacyChoicesUrl",
                "privacyPolicyText",
                "supportUrl",
                "marketingUrl",
            }
            and value
        }
        if app_info_id:
            self._request(
                "PATCH",
                f"/appInfoLocalizations/{app_info_id}",
                json_body={
                    "data": {
                        "type": "appInfoLocalizations",
                        "id": app_info_id,
                        "attributes": app_info_attributes,
                    }
                },
            )
        else:
            for key in ("privacyPolicyUrl", "privacyChoicesUrl", "privacyPolicyText"):
                if preserved.get(key):
                    app_info_attributes[key] = preserved[key]
            created = self._request(
                "POST",
                "/appInfoLocalizations",
                json_body={
                    "data": {
                        "type": "appInfoLocalizations",
                        "attributes": {"locale": target_locale, **app_info_attributes},
                        "relationships": {
                            "appInfo": {"data": {"type": "appInfos", "id": snapshot.app_info_id}}
                        },
                    }
                },
            )
            app_info_id = str(created["data"]["id"])
        if version_localization_id:
            self._request(
                "PATCH",
                f"/appStoreVersionLocalizations/{version_localization_id}",
                json_body={
                    "data": {
                        "type": "appStoreVersionLocalizations",
                        "id": version_localization_id,
                        "attributes": version_attributes,
                    }
                },
            )
        else:
            for key in ("supportUrl", "marketingUrl"):
                if preserved.get(key):
                    version_attributes[key] = preserved[key]
            created = self._request(
                "POST",
                "/appStoreVersionLocalizations",
                json_body={
                    "data": {
                        "type": "appStoreVersionLocalizations",
                        "attributes": {"locale": target_locale, **version_attributes},
                        "relationships": {
                            "appStoreVersion": {
                                "data": {
                                    "type": "appStoreVersions",
                                    "id": snapshot.version_id,
                                }
                            }
                        },
                    }
                },
            )
            version_localization_id = str(created["data"]["id"])
        return {
            "before": before,
            "after": fields,
            "versionId": snapshot.version_id,
            "versionState": snapshot.version_state,
            "appInfoLocalizationId": app_info_id,
            "versionLocalizationId": version_localization_id,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, object] | None = None,
        version: str = "v1",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """One authenticated call; `path` may be a full `links.next` URL from Apple.

        Retries rate limits and transient server errors (honouring `Retry-After`),
        returns `{}` for empty 204 responses, and never logs response bodies.
        """

        url = path if path.startswith("https://") else f"{APP_STORE_CONNECT_ROOT}/{version}{path}"
        if not url.startswith(f"{APP_STORE_CONNECT_ROOT}/"):
            raise AppStoreConnectError("refusing to call a non-App Store Connect URL")
        attempt = 0
        while True:
            token = self._token()
            try:
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=timeout or self.settings.request_timeout,
                )
            except httpx.HTTPError as exc:
                raise AppStoreConnectError("App Store Connect is unavailable") from exc
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                attempt += 1
                self._sleep(_retry_wait(response, attempt))
                continue
            break
        if response.status_code >= 400:
            raise AppStoreConnectError(_error_detail(response), status=response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AppStoreConnectError("App Store Connect returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AppStoreConnectError("App Store Connect returned an unexpected response")
        return payload

    def _get_all(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        version: str = "v1",
        max_pages: int = 50,
        included: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Every item of a collection, following `links.next` pagination.

        When `included` is given, related resources from every page are added to it,
        keyed by (type, id).
        """

        items: list[dict[str, Any]] = []
        payload = self._request("GET", path, params=params, version=version)
        for _page in range(max_pages):
            data = payload.get("data", [])
            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, dict))
            if included is not None:
                for item in payload.get("included", []) or []:
                    if isinstance(item, dict) and "type" in item and "id" in item:
                        included[(str(item["type"]), str(item["id"]))] = item
            next_url = (payload.get("links") or {}).get("next")
            if not next_url:
                break
            payload = self._request("GET", str(next_url))
        return items

    @staticmethod
    def _sleep(seconds: float) -> None:
        time.sleep(seconds)

    def _token(self) -> str:
        settings = self.settings
        if not (
            settings.app_store_connect_issuer_id
            and settings.app_store_connect_key_id
            and settings.app_store_connect_key_path
        ):
            raise AppStoreConnectError("App Store Connect credentials are not configured")
        key_path = Path(settings.app_store_connect_key_path).expanduser()
        if not key_path.is_file():
            raise AppStoreConnectError("the App Store Connect private key was not found")
        if not _key_mode_is_safe(key_path):
            raise AppStoreConnectError(
                "the App Store Connect private key must not be group- or world-readable"
            )
        now = int(time.time())
        payload = {
            "iss": settings.app_store_connect_issuer_id,
            "iat": now,
            "exp": now + 20 * 60,
            "aud": "appstoreconnect-v1",
        }
        try:
            return jwt.encode(
                payload,
                key_path.read_text(encoding="utf-8"),
                algorithm="ES256",
                headers={"kid": settings.app_store_connect_key_id, "typ": "JWT"},
            )
        except Exception as exc:
            raise AppStoreConnectError("could not create the App Store Connect token") from exc


def _retry_wait(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After", "")
    try:
        wait = float(header)
    except ValueError:
        wait = float(2 ** (attempt - 1))
    return max(0.0, min(MAX_RETRY_WAIT_SECONDS, wait))


def _pick_version(versions: list[dict[str, Any]]) -> dict[str, Any]:
    """The newest editable iOS version; else the newest one (writes then refuse clearly)."""

    newest_first = sorted(
        versions,
        key=lambda item: str(item.get("attributes", {}).get("createdDate") or ""),
        reverse=True,
    )
    for item in newest_first:
        if str(item.get("attributes", {}).get("appStoreState") or "") in EDITABLE_VERSION_STATES:
            return item
    return newest_first[0]


def _pick_app_info(app_infos: list[dict[str, Any]]) -> dict[str, Any]:
    """When a new version is being prepared there are two app infos; edit the non-live one."""

    for item in app_infos:
        if str(item.get("attributes", {}).get("state") or "") not in _LIVE_APP_INFO_STATES:
            return item
    return app_infos[0]


def _key_mode_is_safe(path: Path) -> bool:
    if os.name == "nt":
        return True
    try:
        return (path.stat().st_mode & 0o077) == 0
    except OSError:
        return False


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        errors = payload.get("errors", [])
        if errors and isinstance(errors[0], dict):
            return str(errors[0].get("detail") or "App Store Connect rejected the request")
    except (json.JSONDecodeError, TypeError):
        pass
    return f"App Store Connect returned HTTP {response.status_code}"
