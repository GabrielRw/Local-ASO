"""Offline licence keys for the paid Mac app.

A key is ``LASO1-<payload>.<signature>``: base32 (no padding) of a compact JSON payload
and of its Ed25519 signature. Keys are signed by the Stripe key page
(``licence-server/``) or by ``aso licence mint``, and verified here with the public key
below; nothing is sent anywhere to check them.

Local ASO is free: ``PAID_EDITION`` is off, so nothing is gated and the licence UI is
hidden. The code stays so a paid Mac edition can be switched on later. When it is on,
only the desktop build is gated (the Tauri shell sets ``LOCAL_ASO_DESKTOP=1``); the
open-source CLI and the dashboard run from a checkout are never limited, and without a
licence everything works except writes to App Store Connect.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from local_aso_tracker.config import data_dir

# The single switch for the paid Mac edition. False: the app is 100% free.
PAID_EDITION = False

PREFIX = "LASO1-"
PRODUCT = "desktop-lifetime"
PRICE_LABEL = "$9"
# The Stripe Payment Link buyers open from the app. Set before the first release
# (scripts/release-macos.sh refuses to run while it or the public key is empty).
BUY_URL = ""
# Raw Ed25519 public key, base64. Paste the output of
# scripts/generate-licence-keypair.py here. Deliberately not read from the
# environment: that would let anyone substitute their own key.
PUBLIC_KEY_B64 = ""

GATED_FEATURES = {
    "listing-push": "Pushing listings to App Store Connect",
    "price-push": "Changing prices in App Store Connect",
}


class LicenceError(ValueError):
    """A key that doesn't verify, or a gated action without a licence."""


class LicenceRequired(LicenceError):
    """A gated action was attempted without a valid licence."""


@dataclass(frozen=True)
class Licence:
    id: str
    email: str
    issued: str
    product: str


def _b32encode(data: bytes) -> str:
    return base64.b32encode(data).decode().rstrip("=")


def _b32decode(text: str) -> bytes:
    clean = text.strip().upper()
    return base64.b32decode(clean + "=" * (-len(clean) % 8))


def payload_bytes(*, licence_id: str, email: str, issued: str) -> bytes:
    """Canonical payload: sorted keys, no spaces (the Worker builds the same bytes)."""

    return json.dumps(
        {"email": email, "id": licence_id, "issued": issued, "product": PRODUCT, "v": 1},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def mint(
    private_key: Ed25519PrivateKey, *, licence_id: str, email: str, issued: str | None = None
) -> str:
    day = issued or datetime.now(UTC).date().isoformat()
    payload = payload_bytes(licence_id=licence_id, email=email.strip().lower(), issued=day)
    return f"{PREFIX}{_b32encode(payload)}.{_b32encode(private_key.sign(payload))}"


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise LicenceError("that file is not an Ed25519 private key")
    return key


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode()


def verify(key: str, public_key: str | None = None) -> Licence:
    encoded = public_key if public_key is not None else PUBLIC_KEY_B64
    if not encoded:
        raise LicenceError("this build has no licence public key configured")
    text = "".join(key.split())
    if not text.startswith(PREFIX) or "." not in text:
        raise LicenceError("that doesn't look like a Local ASO licence key")
    body, signature = text[len(PREFIX) :].split(".", 1)
    try:
        payload = _b32decode(body)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded)).verify(
            _b32decode(signature), payload
        )
        data = json.loads(payload)
    except (InvalidSignature, ValueError, json.JSONDecodeError) as exc:
        raise LicenceError("that licence key isn't valid") from exc
    if data.get("v") != 1 or data.get("product") != PRODUCT:
        raise LicenceError("that licence key is for a different product")
    return Licence(
        id=str(data.get("id", "")),
        email=str(data.get("email", "")),
        issued=str(data.get("issued", "")),
        product=str(data["product"]),
    )


def licence_path() -> Path:
    return data_dir() / "licence.key"


def is_desktop() -> bool:
    return os.getenv("LOCAL_ASO_DESKTOP") == "1" or bool(getattr(sys, "frozen", False))


def current() -> Licence | None:
    path = licence_path()
    if not path.is_file():
        return None
    try:
        return verify(path.read_text(encoding="utf-8"))
    except LicenceError:
        return None


def activate(key: str) -> Licence:
    licence = verify(key)
    path = licence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(key.split()) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return licence


def remove() -> None:
    licence_path().unlink(missing_ok=True)


def status() -> dict[str, object]:
    licence = current()
    return {
        "desktop": is_desktop(),
        "paidEdition": PAID_EDITION,
        "licensed": licence is not None,
        "required": PAID_EDITION and is_desktop() and licence is None,
        "email": licence.email if licence else None,
        "issued": licence.issued if licence else None,
        "buyUrl": BUY_URL or None,
        "price": PRICE_LABEL,
        "version": os.getenv("LOCAL_ASO_VERSION") or _package_version(),
    }


def require(feature: str) -> None:
    """Refuse a gated action in the unlicensed paid desktop app (no-op everywhere else)."""

    if PAID_EDITION and is_desktop() and current() is None:
        action = GATED_FEATURES.get(feature, "This action")
        raise LicenceRequired(
            f"{action} needs a Local ASO licence ({PRICE_LABEL}, lifetime). "
            "Add your key under Settings → Licence."
        )


def _package_version() -> str:
    from local_aso_tracker import __version__

    return __version__
