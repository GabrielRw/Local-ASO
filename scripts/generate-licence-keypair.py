"""Create the Ed25519 key pair that signs Local ASO licence keys.

Usage: uv run python scripts/generate-licence-keypair.py <private-key-path>

The private key (PEM, mode 600) is written where you say, never into this
repository. Store it in your password manager and as the Worker secret
LICENCE_PRIVATE_KEY. The printed public key goes into
src/local_aso_tracker/licensing.py (PUBLIC_KEY_B64) and
licence-server/wrangler.toml (LICENCE_PUBLIC_KEY, used for a self-check).
"""

from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_aso_tracker.licensing import public_key_b64


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1]).expanduser().resolve()
    repo = Path(__file__).resolve().parents[1]
    if target.is_relative_to(repo):
        raise SystemExit("refusing to write the private key inside the repository")
    if target.exists():
        raise SystemExit(f"{target} already exists; not overwriting a signing key")
    key = Ed25519PrivateKey.generate()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    target.chmod(0o600)
    print(f"Private key written to {target}")
    print(f"Public key (PUBLIC_KEY_B64): {public_key_b64(key)}")


if __name__ == "__main__":
    main()
