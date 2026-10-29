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
    assert 'id="localizeKeywordsButton"' in html
    assert 'id="localizationPreview"' in html
    assert 'id="appTooltip"' in html
    assert 'id="deleteAppModal"' in html
    assert 'id="confirmDeleteApp"' in html
    assert 'id="overallRankChart"' in html
    assert 'id="overallAverageRank"' in html
    assert 'id="countryVisibility"' in html
    assert 'id="losingCard"' in html
    assert 'id="losingGrid"' in html
    assert 'id="metricHistoryModal"' in html
    assert 'id="metricHistoryChart"' in html
    assert 'id="coverageCard"' in html
    assert "window.confirm" not in script
    assert "targetsReactivated" in script
    assert "screenshotStatus" in script
    assert "countryFlag" in script
    assert "keywordsRequested" in script
    assert "automaticCheck" in script
    assert "estimateCell" in script
    assert "volumeEstimate" in script
    assert "difficultyEstimate" in script
    assert "topAppsCell" in script
    assert "rankingHeaderClick" in script
    assert "sortRankingRows" in script
    assert 'id="rankingsHeader"' in html
    assert 'data-rank-sort="volume"' in html
    assert ".rank-sort-button" in styles
    assert "showTopAppTooltip" in script
    assert "app-delete-button" in script
    assert "/api/apps/deactivate" in script
    assert "metricTrend" in script
    assert "queuedCheckTargets" in script
    assert "row-check-state" in script
    assert ".row-check-state" in styles
    assert "metricTrends30d" in script
    assert 'label: "Tracked"' not in script
    assert 'label: "Not visible"' not in script
    assert "renderOverallRankHistory" in script
    assert "renderLosingTo" in script
    assert "losingRatingMarkup" in script
    assert ".losing-rating" in styles
    assert "renderCountryVisibility" in script
    assert "data-country-card" in script
    assert "monitorAutomaticSync" in script
    assert "/api/sync-status" in script
    assert 'id="syncIndicator"' in html
    assert 'id="paidSearchPanel"' in html
    assert 'id="appleAdsContent"' in html
    assert "loadAppleAds" in script
    assert "/api/apple-ads/sync" in script
    assert "appleAdsKeywordRow" in script
    assert "appleAdsShowPaused" in script
    assert "Show paused" in script
    assert "paidCountryFilterButton" in script
    assert "paidSortHeader" in script
    assert "/api/keywords/check-rank" in script
    assert "checkPaidKeywordRank" in script
    assert ".paid-country-filter" in styles
    assert ".paid-aso-rank" in styles
    assert 'id="topAppMenu"' in html
    assert 'id="competitorMatrix"' in html
    assert "addPendingTopAppCompetitor" in script
    assert "competitorMatrixAction" in script
    assert "/api/competitors/refresh" in script
    assert ".competitor-matrix-table" in styles
    assert "openMetricHistory" in script
    assert "data-metric-series" in script
    assert "renderListingCoverage" in script
    assert "/api/listing-metadata" in script
    assert "coverageGoalOption" in script
    assert "Untracked keyword matches" in script
    assert "coverage-match-sections" in styles
    assert "Word-by-word analysis" not in script
    assert "coverage-principle" in styles
    assert "coverage-goal-list" in script
    assert ".coverage-setup-fields" in styles
    assert "coverage-word-table" not in styles
    assert "coverage-terms" not in script
    assert "coverage-terms" not in styles
    assert 'id="coverageLiveNameMirror"' in script
    assert "coverage-token-shell" in styles
    assert "coverage-highlight-list" not in styles
    assert "keywordCoverageConfigured" in script
    assert "healthAuditButton" in script
    assert ".health-layout.audit-locked" in styles
    assert ".score-ring.score-ring-setup" in styles
    assert 'id="nicheWorkspace"' in html
    assert 'id="nicheCheckNowButton"' in html
    assert 'id="nicheAgentForm"' in html
    assert "nicheCheckSummary" in script
    assert "No rated matches" in script
    assert "volumeTone" in script
    assert "difficultyTone" in script
    assert ".niche-cell-inner.mixed" in styles
    assert ".niche-cell-inner { min-height: 21px;" in styles
    assert "Live methodology" not in html
    assert 'aria-labelledby="appModalTitle"' in html
    assert 'aria-labelledby="keywordModalTitle"' in html
    assert 'aria-labelledby="confirmModalTitle"' in html
    assert 'aria-labelledby="deleteAppModalTitle"' in html
    assert "refreshCustomSelects" in script
    assert "enhanceSelect" in script
    assert "renderCustomSelectMenu" in script
    assert "handleCustomSelectMenuKeydown" in script
    assert "custom-select-menu" in script
    assert "custom-select-trigger" in styles
    assert ".custom-select-menu" in styles
    assert "dialog.modal" in styles
    assert "modal-surface-in" in styles
    assert "custom-select-native" in styles
    assert ".competitor-remove,\n.sidebar-foot .setup-link {\n  border: 0;" in styles
    assert ">Growth toolkit<" not in html
    assert 'id="appCount"' not in html
    assert "Search visibility" not in html
    assert "Apple public data" not in script
    assert "@media (max-width: 800px)" in styles


def test_dashboard_does_not_accept_or_render_apple_ads_secret_material() -> None:
    static = files("local_aso_tracker.web").joinpath("static")
    for filename in ("index.html", "app.js", "onboarding.js", "styles.css"):
        content = static.joinpath(filename).read_text(encoding="utf-8").lower()
        for retired in (
            "private.jwt.token",
            "signed es256 jwt",
            "client_secret=",
            "apple-ads.toml",
        ):
            assert retired not in content, f"{retired} remains in {filename}"
    html = static.joinpath("index.html").read_text(encoding="utf-8")
    assert html.count("data-setup-step=") == 3
    assert html.count("data-setup-progress=") == 3
    assert "No account or API keys needed" not in html
    assert 'id="onboardingAgentChoices"' in html


def test_dashboard_has_no_aso_principle_audit() -> None:
    static = files("local_aso_tracker.web").joinpath("static")
    for filename in ("index.html", "app.js", "styles.css"):
        content = static.joinpath(filename).read_text(encoding="utf-8").lower()
        for retired in ("aso principle audit", "metadataaudit", "listing-audit", "listingaudit"):
            assert retired not in content, f"{retired} remains in {filename}"
