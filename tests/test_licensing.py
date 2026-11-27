"""Offline licence keys, the desktop-only gate, and the licence routes."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_aso_tracker import __version__, licensing
from local_aso_tracker.database import run_migrations
from local_aso_tracker.web import server as server_module
from local_aso_tracker.web.server import DashboardHandler, LocalDashboardServer

ROOT = Path(__file__).resolve().parents[1]
VECTOR = json.loads((ROOT / "tests/fixtures/licence_vector.json").read_text())


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Ed25519PrivateKey:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("LOCAL_ASO_DESKTOP", raising=False)
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(VECTOR["seedHex"]))
    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", VECTOR["publicKey"])
    # The gate tests exercise the paid edition; the shipped default is free.
    monkeypatch.setattr(licensing, "PAID_EDITION", True)
    return key


def test_shared_vector_matches_minting(keys: Ed25519PrivateKey) -> None:
    minted = licensing.mint(
        keys, licence_id=VECTOR["id"], email=VECTOR["email"], issued=VECTOR["issued"]
    )
    assert minted == VECTOR["key"]  # Ed25519 is deterministic: the Worker gets the same key
    licence = licensing.verify(VECTOR["key"])
    assert (licence.email, licence.id, licence.issued) == (
        "buyer@example.com",
        "cs_test_a1B2c3D4",
        "2026-11-19",
    )
    # Whitespace and line breaks from an email are tolerated.
    spaced = VECTOR["key"][:20] + "\n " + VECTOR["key"][20:]
    assert licensing.verify(spaced).email == "buyer@example.com"


def test_tampered_foreign_and_garbage_keys_are_refused(keys: Ed25519PrivateKey) -> None:
    body, signature = VECTOR["key"][len(licensing.PREFIX) :].split(".")
    other = licensing.mint(
        keys, licence_id="x", email="someone.else@example.com", issued="2026-11-19"
    )
    forged = licensing.PREFIX + other[len(licensing.PREFIX) :].split(".")[0] + "." + signature
    with pytest.raises(licensing.LicenceError, match="isn't valid"):
        licensing.verify(forged)
    stranger = Ed25519PrivateKey.generate()
    with pytest.raises(licensing.LicenceError, match="isn't valid"):
        licensing.verify(licensing.mint(stranger, licence_id="x", email="a@b.c"))
    for garbage in ("", "hello", "LASO1-", "LASO1-AAAA.BBBB", f"LASO1-{body}"):
        with pytest.raises(licensing.LicenceError):
            licensing.verify(garbage)


def test_builds_without_a_public_key_refuse_every_key(
    keys: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", "")
    with pytest.raises(licensing.LicenceError, match="no licence public key"):
        licensing.verify(VECTOR["key"])


def test_gate_applies_only_to_the_desktop_app(
    keys: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    licensing.require("price-push")  # checkout / CLI: never gated
    monkeypatch.setenv("LOCAL_ASO_DESKTOP", "1")
    with pytest.raises(licensing.LicenceRequired, match="Changing prices"):
        licensing.require("price-push")
    licensing.activate(VECTOR["key"])
    assert oct(licensing.licence_path().stat().st_mode & 0o777) == "0o600"
    licensing.require("price-push")
    assert licensing.status()["email"] == "buyer@example.com"
    licensing.remove()
    assert licensing.status()["required"] is True


@pytest.fixture
def desktop_server(keys: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("LOCAL_ASO_DESKTOP", "1")
    run_migrations()
    server = LocalDashboardServer(("127.0.0.1", 0), DashboardHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_unlicensed_desktop_pushes_get_402_without_reaching_apple(
    desktop_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def record(name: str) -> Any:
        def fake(*_args: object, **_kwargs: object) -> dict[str, object]:
            calls.append(name)
            return {"results": []}

        return fake

    monkeypatch.setattr(server_module, "push_localization", record("listing"))
    monkeypatch.setattr(server_module.pricing, "push_prices", record("prices"))
    routes = {
        "/api/localization-studio/push": {"draftId": 1},
        "/api/pricing/push": {"appId": 1, "kind": "app", "id": "1", "changes": []},
    }
    with httpx.Client(base_url=desktop_server, trust_env=False) as client:
        for path, body in routes.items():
            response = client.post(path, json=body, headers={"Origin": desktop_server})
            assert response.status_code == 402, path
            assert "licence" in response.json()["error"]
        assert calls == []

        status = client.get("/api/licence").json()
        assert status["desktop"] is True and status["required"] is True
        assert status["settings"] == {"checkUpdates": True}

        bad = client.post("/api/licence", json={"key": "LASO1-nope.nope"})
        assert bad.status_code == 400
        cross = client.post(
            "/api/licence", json={"key": VECTOR["key"]}, headers={"Origin": "https://evil.example"}
        )
        assert cross.status_code == 403
        ok = client.post(
            "/api/licence", json={"key": VECTOR["key"]}, headers={"Origin": desktop_server}
        )
        assert ok.status_code == 200 and ok.json()["licensed"] is True
        assert "key" not in ok.json()  # the key itself is never echoed back

        for path, body in routes.items():
            assert client.post(path, json=body).status_code == 200, path
        assert calls == ["listing", "prices"]

        updates = client.post("/api/desktop/settings", json={"checkUpdates": False})
        assert updates.json()["settings"] == {"checkUpdates": False}
        removed = client.post("/api/licence", json={"remove": True})
        assert removed.json()["licensed"] is False


def test_desktop_settings_file_is_what_the_shell_reads(keys: Ed25519PrivateKey) -> None:
    from local_aso_tracker.desktop import desktop_settings_path, save_desktop_settings

    save_desktop_settings({"checkUpdates": False, "unknown": True})
    assert json.loads(desktop_settings_path().read_text()) == {"checkUpdates": False}


def test_every_version_number_matches() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    tauri = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text())["version"]
    cargo = tomllib.loads((ROOT / "desktop/src-tauri/Cargo.toml").read_text())["package"]["version"]
    package = json.loads((ROOT / "desktop/package.json").read_text())["version"]
    assert {pyproject, tauri, cargo, package, __version__} == {__version__}
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_the_free_edition_never_gates_and_hides_the_licence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOCAL_ASO_DESKTOP", "1")
    assert licensing.PAID_EDITION is False
    licensing.require("listing-push")
    licensing.require("price-push")
    status = licensing.status()
    assert status["paidEdition"] is False and status["required"] is False


def test_desktop_server_stops_when_the_app_disappears() -> None:
    from local_aso_tracker.web.server import watch_parent

    parents = iter([100, 100, 1])
    stopped: list[bool] = []
    watch_parent(
        100, on_orphaned=lambda: stopped.append(True), getppid=lambda: next(parents), interval=0
    )
    assert stopped == [True]
