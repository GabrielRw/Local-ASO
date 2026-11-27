"""Write the Tauri updater feed (latest.json) for one macOS release.

Usage: python3 scripts/write-update-feed.py <folder> <version> <notes> <tarball-url>

<folder> must contain the updater tarball's signature as ``*.app.tar.gz.sig``.
Runs on the system Python (3.9 on macOS), so it avoids newer standard-library names.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    folder, version, notes, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    signatures = sorted(folder.glob("*.app.tar.gz.sig"))
    if len(signatures) != 1:
        raise SystemExit(f"expected one .app.tar.gz.sig in {folder}")
    feed = {
        "version": version,
        "notes": notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),  # noqa: UP017
        "platforms": {
            "darwin-aarch64": {"signature": signatures[0].read_text().strip(), "url": url}
        },
    }
    (folder / "latest.json").write_text(json.dumps(feed, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {folder / 'latest.json'}")


if __name__ == "__main__":
    main()
