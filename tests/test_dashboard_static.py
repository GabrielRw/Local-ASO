"""The packaged dashboard build: present, CSP-compatible, and free of secrets.

The UI source lives in `frontend/` (React); its production build is committed to
`src/local_aso_tracker/web/static/` so the dashboard runs without Node.
"""

from __future__ import annotations

import re
from importlib.resources import files

STATIC = files("local_aso_tracker.web").joinpath("static")


def _assets(suffix: str) -> dict[str, str]:
    folder = STATIC.joinpath("assets")
    return {
        item.name: item.read_text(encoding="utf-8")
        for item in folder.iterdir()
        if item.name.endswith(suffix)
    }


def test_built_dashboard_is_packaged() -> None:
    html = STATIC.joinpath("index.html").read_text(encoding="utf-8")
    assert "<title>Local ASO</title>" in html
    assert 'id="root"' in html
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert scripts, "the build must reference its entry script"
    for name in re.findall(r'(?:src|href)="\./assets/([^"]+)"', html):
        assert STATIC.joinpath("assets", name).is_file(), name
    assert _assets(".js")
    assert _assets(".css")


def test_build_respects_the_dashboard_csp() -> None:
    html = STATIC.joinpath("index.html").read_text(encoding="utf-8")
    # script-src 'self': every script is an external, same-origin module.
    for tag, body in re.findall(r"(<script\b[^>]*>)(.*?)</script>", html, flags=re.S):
        assert 'src="./' in tag, tag
        assert body.strip() == "", "inline scripts are blocked by the CSP"
    # Only relative asset URLs; no CDN scripts, styles, or fonts.
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert url.startswith("./"), url
    for name, css in _assets(".css").items():
        external = re.findall(r"url\(\s*['\"]?(https?:)?//", css)
        assert not external, f"{name} loads an external resource"
        assert "@import url(" not in css, name
    for name, script in _assets(".js").items():
        assert "fonts.googleapis.com" not in script, name
        assert "cdn.jsdelivr" not in script and "unpkg.com" not in script, name


def test_build_contains_no_secret_material_or_retired_features() -> None:
    bundle = "\n".join(
        [
            STATIC.joinpath("index.html").read_text(encoding="utf-8"),
            *_assets(".js").values(),
            *_assets(".css").values(),
        ]
    ).lower()
    for secret in ("private.jwt.token", "signed es256 jwt", "client_secret=", "apple-ads.toml"):
        assert secret not in bundle
    for retired in ("aso principle audit", "listing-audit", "listingaudit"):
        assert retired not in bundle


def test_build_carries_the_product_display_rules() -> None:
    script = "\n".join(_assets(".js").values())
    # Missing ranks, estimate labels, and Apple's popularity floor (see frontend/src/lib/format.ts).
    assert "not Apple search volume" in script
    assert "too few searches for Apple to rank" in script
    assert "Competitor names people search" in script
    for endpoint in ("/api/bootstrap", "/api/audits", "/api/keywords", "/api/sync-status"):
        assert endpoint in script
