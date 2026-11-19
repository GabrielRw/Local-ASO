#!/usr/bin/env bash
# Build the Local ASO macOS app: frontend -> frozen Python server -> Tauri bundle.
#
# Output: desktop/src-tauri/target/release/bundle/{macos/Local ASO.app,dmg/*.dmg}
# Requires: uv, pnpm (Node), Rust (cargo), Xcode command line tools.
#
# The app is ad-hoc signed ("-"). For distribution, sign with a Developer ID and
# notarize (see README "Desktop app"): set APPLE_SIGNING_IDENTITY, APPLE_ID,
# APPLE_PASSWORD and APPLE_TEAM_ID before running; Tauri picks them up.
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

echo "==> Tauri app"
pnpm --dir "$ROOT/desktop" install --frozen-lockfile
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  pnpm --dir "$ROOT/desktop" tauri build --config "{\"bundle\":{\"macOS\":{\"signingIdentity\":\"$APPLE_SIGNING_IDENTITY\"}}}"
else
  pnpm --dir "$ROOT/desktop" tauri build
fi

echo "==> Done"
ls -1 "$ROOT/desktop/src-tauri/target/release/bundle/macos" "$ROOT/desktop/src-tauri/target/release/bundle/dmg" 2>/dev/null
