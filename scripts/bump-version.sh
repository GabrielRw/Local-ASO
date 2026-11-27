#!/usr/bin/env bash
# Set one version everywhere it lives: Python package, Tauri app, Rust crate, desktop npm package.
# Usage: scripts/bump-version.sh 0.6.0
set -euo pipefail

VERSION="${1:-}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 MAJOR.MINOR.PATCH" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$ROOT" "$VERSION" <<'PY'
import json, re, sys
from pathlib import Path

root, version = Path(sys.argv[1]), sys.argv[2]

def sub(path: str, pattern: str, replacement: str) -> None:
    file = root / path
    text, count = re.subn(pattern, replacement, file.read_text(), count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"version not found in {path}")
    file.write_text(text)

sub("pyproject.toml", r'^version = "[^"]+"', f'version = "{version}"')
sub("src/local_aso_tracker/__init__.py", r'^__version__ = "[^"]+"', f'__version__ = "{version}"')
sub("desktop/src-tauri/Cargo.toml", r'^version = "[^"]+"', f'version = "{version}"')
for path in ("desktop/src-tauri/tauri.conf.json", "desktop/package.json"):
    file = root / path
    data = json.loads(file.read_text())
    data["version"] = version
    file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print(f"Version set to {version}")
PY
(cd "$ROOT" && uv lock --quiet >/dev/null 2>&1 || true)
(cd "$ROOT/desktop/src-tauri" && cargo update --quiet --package local-aso --precise "$VERSION" >/dev/null 2>&1 || true)
