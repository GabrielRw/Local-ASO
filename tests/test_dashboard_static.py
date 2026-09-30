"""Packaged dashboard asset regression tests."""

from importlib.resources import files


def test_dashboard_assets_are_packaged_with_required_workflows() -> None:
    static = files("local_aso_tracker.web").joinpath("static")
    html = static.joinpath("index.html").read_text(encoding="utf-8")
    script = static.joinpath("app.js").read_text(encoding="utf-8")
    styles = static.joinpath("styles.css").read_text(encoding="utf-8")

    assert 'id="keywordModal"' in html
    assert 'id="appModal"' in html
    assert 'id="confirmModal"' in html
    assert 'id="comparisonCard"' in html
    assert 'id="screenshotGallery"' in html
    assert 'id="deviceSelect"' in html
    assert 'id="deviceChecks"' in html
    assert "window.confirm" not in script
    assert "targetsReactivated" in script
    assert "screenshotStatus" in script
    assert "countryFlag" in script
    assert "keywordsRequested" in script
    assert "automaticCheck" in script
    assert "@media (max-width: 800px)" in styles


def test_dashboard_has_no_popularity_or_credentials_workflow() -> None:
    static = files("local_aso_tracker.web").joinpath("static")
    for filename in ("index.html", "app.js", "onboarding.js", "styles.css"):
        content = static.joinpath(filename).read_text(encoding="utf-8").lower()
        for retired in ("popularity", "appleads", "apple-ads", "oauth", "clientsecret"):
            assert retired not in content, f"{retired} remains in {filename}"
    html = static.joinpath("index.html").read_text(encoding="utf-8")
    assert html.count("data-setup-step=") == 2
    assert html.count("data-setup-progress=") == 2
    assert "No account or API keys needed" in html


def test_dashboard_has_no_aso_principle_audit() -> None:
    static = files("local_aso_tracker.web").joinpath("static")
    for filename in ("index.html", "app.js", "styles.css"):
        content = static.joinpath(filename).read_text(encoding="utf-8").lower()
        for retired in ("aso principle audit", "metadataaudit", "listing-audit", "listingaudit"):
            assert retired not in content, f"{retired} remains in {filename}"
