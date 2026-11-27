#!/usr/bin/env bash
# Build a signed, notarized, auto-updatable Local ASO release and prepare its GitHub Release.
#
# Usage: scripts/release-macos.sh "Release notes, one line or Markdown"
#
# Needs (see README "Releasing"):
#   APPLE_SIGNING_IDENTITY   "Developer ID Application: Name (TEAMID)"
#   APPLE_API_KEY, APPLE_API_ISSUER, APPLE_API_KEY_PATH   notarization (App Store Connect API key)
#   TAURI_SIGNING_PRIVATE_KEY (+ TAURI_SIGNING_PRIVATE_KEY_PASSWORD)   updater signature
# and, in the source: the licence public key, the Stripe buy URL, the updater pubkey.
#
# Nothing is published: the script prints the `gh release create` command for you to run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTES="${1:-}"
fail() { echo "release: $*" >&2; exit 1; }

[[ -n "$NOTES" ]] || fail "pass release notes as the first argument"
for name in APPLE_SIGNING_IDENTITY APPLE_API_KEY APPLE_API_ISSUER APPLE_API_KEY_PATH TAURI_SIGNING_PRIVATE_KEY; do
  [[ -n "${!name:-}" ]] || fail "$name is not set"
done
[[ "$APPLE_SIGNING_IDENTITY" == "Developer ID Application:"* ]] \
  || fail "APPLE_SIGNING_IDENTITY must be a 'Developer ID Application' certificate"
security find-identity -v -p codesigning | grep -qF "$APPLE_SIGNING_IDENTITY" \
  || fail "the signing certificate is not in your keychain"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || fail "commit or stash your changes first"

CONF="$ROOT/desktop/src-tauri/tauri.conf.json"
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$CONF")"
PUBKEY="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"]["updater"]["pubkey"])' "$CONF")"
[[ -n "$PUBKEY" ]] || fail "set plugins.updater.pubkey in tauri.conf.json (pnpm --dir desktop tauri signer generate)"
grep -qE '^PUBLIC_KEY_B64 = "[A-Za-z0-9+/=]{40,}"' "$ROOT/src/local_aso_tracker/licensing.py" \
  || fail "set PUBLIC_KEY_B64 in licensing.py (scripts/generate-licence-keypair.py)"
grep -qE '^BUY_URL = "https://' "$ROOT/src/local_aso_tracker/licensing.py" \
  || fail "set BUY_URL in licensing.py to your Stripe Payment Link"
if git -C "$ROOT" rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
  fail "tag v$VERSION already exists; run scripts/bump-version.sh first"
fi

BUNDLE="$ROOT/desktop/src-tauri/target/release/bundle"
OUT="$BUNDLE/release-v$VERSION"
[[ ! -e "$OUT" ]] || fail "$OUT already exists; move it away first"

"$ROOT/scripts/build-macos.sh" --config '{"bundle":{"createUpdaterArtifacts":true}}'

APP="$BUNDLE/macos/Local ASO.app"
DMG="$(ls "$BUNDLE"/dmg/*.dmg | head -1)"
TARBALL="$BUNDLE/macos/Local ASO.app.tar.gz"
[[ -f "$TARBALL" && -f "$TARBALL.sig" ]] || fail "updater artifacts are missing"

echo "==> Verifying signature and notarization"
codesign --verify --deep --strict --verbose=2 "$APP"
spctl --assess --type execute --verbose=2 "$APP"
xcrun stapler validate "$APP"

ASSET="Local.ASO.app.tar.gz" # GitHub turns spaces in asset names into dots
mkdir -p "$OUT"
cp "$DMG" "$OUT/Local.ASO_${VERSION}_aarch64.dmg"
cp "$TARBALL" "$OUT/$ASSET"
cp "$TARBALL.sig" "$OUT/$ASSET.sig"
python3 "$ROOT/scripts/write-update-feed.py" "$OUT" "$VERSION" "$NOTES" \
  "https://github.com/GabrielRw/Local-ASO/releases/download/v$VERSION/$ASSET"

echo
echo "==> Ready in $OUT. Review it, then publish with:"
echo "git tag v$VERSION && git push origin v$VERSION"
printf 'gh release create v%s --repo GabrielRw/Local-ASO --title "Local ASO %s" --notes %q %q %q %q %q\n' \
  "$VERSION" "$VERSION" "$NOTES" "$OUT/Local.ASO_${VERSION}_aarch64.dmg" "$OUT/$ASSET" \
  "$OUT/$ASSET.sig" "$OUT/latest.json"
