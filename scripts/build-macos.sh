#!/usr/bin/env bash
# Build the Local ASO macOS app: frontend -> frozen Python server -> Tauri bundle.
#
# Output: desktop/src-tauri/target/release/bundle/{macos/Local ASO.app,dmg/*.dmg}
# Requires: uv, pnpm (Node), Rust (cargo), Xcode command line tools.
#
# The app is ad-hoc signed ("-") unless APPLE_SIGNING_IDENTITY names a
# "Developer ID Application" certificate. Then every binary in the frozen server is
# signed with the hardened runtime first (Tauri doesn't sign files in Resources, and
# notarization rejects unsigned nested code), and Tauri signs and notarizes the app
# with APPLE_API_KEY / APPLE_API_ISSUER / APPLE_API_KEY_PATH. See docs/GUIDE.md "Releasing".
#
# Extra arguments are passed to `tauri build` (scripts/release-macos.sh uses this).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.cargo/bin:$PATH"

echo "==> Frontend"
pnpm --dir "$ROOT/frontend" install --frozen-lockfile
pnpm --dir "$ROOT/frontend" build

echo "==> Bundled Python server"
rm -rf "$ROOT/desktop/build/aso-server"
(
  cd "$ROOT"
  uv run --with pyinstaller pyinstaller --noconfirm --log-level WARN \
    --distpath desktop/build --workpath desktop/build/pyinstaller desktop/aso-server.spec
)
"$ROOT/desktop/build/aso-server/aso-server" --help >/dev/null

if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  echo "==> Signing the bundled server's binaries"
  # Mach-O files only, deepest first; the main executable last.
  while IFS= read -r -d '' file; do
    if file -b "$file" | grep -q "Mach-O"; then
      codesign --force --options runtime --timestamp \
        --entitlements "$ROOT/desktop/aso-server.entitlements" \
        --sign "$APPLE_SIGNING_IDENTITY" "$file"
    fi
  done < <(find "$ROOT/desktop/build/aso-server" -type f ! -path "*/aso-server/aso-server" -print0)
  codesign --force --options runtime --timestamp \
    --entitlements "$ROOT/desktop/aso-server.entitlements" \
    --sign "$APPLE_SIGNING_IDENTITY" "$ROOT/desktop/build/aso-server/aso-server"
fi

echo "==> Tauri app"
pnpm --dir "$ROOT/desktop" install --frozen-lockfile
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  pnpm --dir "$ROOT/desktop" tauri build "$@" --config "{\"bundle\":{\"macOS\":{\"signingIdentity\":\"$APPLE_SIGNING_IDENTITY\"}}}"
else
  pnpm --dir "$ROOT/desktop" tauri build "$@"
fi

echo "==> Done"
ls -1 "$ROOT/desktop/src-tauri/target/release/bundle/macos" "$ROOT/desktop/src-tauri/target/release/bundle/dmg" 2>/dev/null
