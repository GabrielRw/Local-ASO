# Local ASO Tracker

Local ASO Tracker is an open-source, local-first App Store keyword rank tracker with a Python CLI and a browser dashboard. Track multiple iOS apps across countries and iPhone/iPad search results, keep historical checks in SQLite, and export your data without a hosted ASO subscription.

There is no Local ASO account, cloud database, telemetry, analytics SDK, third-party ASO API, browser automation, or App Store HTML scraping. Core rank tracking uses Apple’s public iTunes Search API. An optional read-only Apple Ads integration can import campaign targeting, bids, and performance when local API OAuth credentials are supplied. The dashboard can render artwork and screenshots hosted by Apple. No Apple login is required; Apple Ads OAuth credentials are optional.

> This tracks public search-result positions, not guaranteed on-device App Store ranks. Apple does not expose search volume or downloads, so the dashboard's volume and difficulty values are clearly labeled local estimates derived from matching-app ratings.

## Features

- Local dashboard with app switching, country flags, and separate iPhone/iPad rankings.
- Batch keyword entry using commas or new lines, with an automatic first check.
- Curated English, French, and Spanish keyword localization with a preview before adding targets.
- Current ranks, rank changes, rank-history charts, and rank-based opportunity groups.
- Overall daily average-rank trend for all tracked keywords in the selected storefront and device.
- Non-blocking full-catalog synchronization at dashboard startup and once every 24 hours while it remains open.
- “Losing to” leaderboard counting Top 5 competitors that appear ahead across the current keyword set.
- Competitor keyword matrix with apps as columns, tracked keywords as rows, and refreshed rank positions.
- Ratings-based audience and top-10 competition estimates, stored separately with each successful check.
- App-wide Niche research boards powered by a locally installed Codex or Claude CLI, with unlimited country columns and on-demand refreshes.
- Optional read-only Apple Ads reporting for current targeting keywords, bids, spend, taps, installs, and Apple keyword suggestions.
- The first five returned apps for each keyword, displayed as Apple artwork with hover/focus names.
- Public listing-health review, screenshot previews when available, and competitor comparison.
- Three-step listing strategy audit with distribution goal, brand term, highlighted duplication checks, and title-order verification.
- CLI commands for managing apps, keywords, storefronts, and tracking targets.
- CSV/JSON exports and a self-contained HTML report that can be opened offline.
- SQLite persistence, idempotent setup, and optional scheduling through your operating system.

## Contents

- [Quick start](#quick-start)
- [Using the dashboard](#using-the-dashboard)
- [Niche research](#niche-research)
- [Competitor keyword matrix](#competitor-keyword-matrix)
- [Apple Ads reporting](#apple-ads-reporting)
- [Local MCP server](#local-mcp-server)
- [CLI-only first setup](#cli-only-first-setup)
- [Ranking methodology and limits](#what-it-measuresand-what-it-does-not)
- [Storage and configuration](#storage-and-configuration)
- [CLI command reference](#initialization)
- [Exports and report](#exports-and-report)
- [Scheduling](#local-scheduling), [backup](#backup-and-restore), and [troubleshooting](#troubleshooting)
- [Development](#development)

## Quick start

You need Git and [`uv`](https://docs.astral.sh/uv/getting-started/installation/). The app requires Python 3.12 or newer; `uv` can obtain the version specified in `.python-version` if needed. The dashboard has no Node.js, npm, or frontend build requirement.

Common ways to install `uv`:

```bash
# macOS with Homebrew
brew install uv
```

```powershell
# Windows with WinGet
winget install --id=astral-sh.uv -e
```

For Linux or other installation methods, follow the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Restart your terminal if `uv` is not found after installation.

Clone the repository and start the dashboard:

```bash
git clone https://github.com/GabrielRw/Local-ASO.git
cd Local-ASO
uv sync --locked
uv run aso dashboard
```

The command initializes the database and opens [http://127.0.0.1:8765/](http://127.0.0.1:8765/) in your default browser. Keep the terminal running while you use the dashboard; press `Ctrl+C` there to stop it.

On the first launch, the three-step setup guide asks you to:

1. Paste your app’s App Store URL or numerical app ID and choose its storefront.
2. Enter keywords separated by commas or new lines, select iPhone or iPad, and open the dashboard. Keywords are optional; if supplied, their first ranking check runs automatically.
3. Choose Auto-detect, Codex, or Claude as the preferred local agent for Niche research. Unavailable CLIs are disabled.

For example, the app ID in `https://apps.apple.com/us/app/example/id123456789` is `123456789`. Use your real App Store ID, not your bundle ID or an Apple Ads account ID.

To launch again later, run `uv run aso dashboard` from the same checkout. Your local data is retained. To start without opening a browser, or to use another port:

```bash
uv run aso dashboard --no-open
uv run aso dashboard --no-open --port 8766
```

When using a different port, open the URL printed in the terminal. On Windows, the same `git`, `uv sync`, and `uv run` commands work in PowerShell.

The dashboard also starts a local MCP endpoint at `http://127.0.0.1:8766/mcp`. Use `--no-mcp` to disable it or `--mcp-port` to choose another loopback port:

```bash
uv run aso dashboard --no-open
uv run aso dashboard --no-open --mcp-port 8767
uv run aso dashboard --no-open --no-mcp
```

## Using the dashboard

1. **Choose an app.** Use the app list in the left sidebar. **+ Add app** imports another app by numerical App Store ID; its public name and listing details come from Apple. The small **×** on an app row removes it from the visible workspace after confirmation while preserving its tracking and history. Adding the same App Store ID again restores it.
2. **Choose a country and device.** The storefront and device selectors control the visible ranking rows. iPhone and iPad have independent tracking targets and history; changing devices does not combine their ranks.
3. **Add keywords.** Click **+ Add keyword**, enter terms such as `notes, quick notes, daily journal`, then select one or more storefronts and devices. Duplicates are ignored. Each selected combination receives an automatic first rank check. **Localize selected** previews curated French and Spanish market phrases before anything is added.
4. **Refresh results.** Use **Run check** for the selected app, storefront, and device. A target with a successful check in the last 24 hours is skipped, while missing, failed, or stale checks remain eligible. Later checks create history rather than overwriting previous results, and Apple failures are reported so you can retry.
5. **Explore history.** Filter the keyword table, then click a keyword row to see its historical ranks. Better ranks are shown higher in the chart. The **Overall rank trend** card at the bottom aggregates the daily average of found keywords across the selected storefront/device. Use **×** to stop tracking a target without deleting its existing history.
6. **Review the listing.** The **Listing health** tab shows a public-data completeness heuristic, a score breakdown, screenshots when Apple returns their URLs, and suggested improvements. This is not an Apple score.
7. **Audit listing strategy.** In **Listing health**, first choose **ASO / SEO / AEO** or **UGC / Ads**, confirm the brand term and storefront, then paste the subtitle and keyword field from App Store Connect. The audit checks repeated words across title, subtitle, and keyword field; verifies the goal-specific title order; and separates tracked keyword matches from metadata terms that are not yet tracked.
8. **Compare apps.** Open a keyword’s Top 5 result stack under **Keywords**, click an app icon, and choose **Add to competitors**. The **Competitors** tab then shows the keyword-by-app rank matrix. The existing public-listing comparison remains lower on the same tab.
9. **Review paid search.** When Apple Ads OAuth credentials are configured, open **Paid search** to discover the accessible ad account, import current campaigns and targeting keywords, and compare Apple-reported spend and installs. The panel also shows suggestions seeded by the app’s best ASO keywords.

**Setup guide** in the sidebar reopens onboarding anytime. The default storefront catalog includes Australia, Canada, France, the United Kingdom, and the United States. To add another storefront, use the [country CLI commands](#countries), then refresh the dashboard.

The dashboard is a local tool without authentication. Keep the default loopback address; do not expose it on a public server or bind it to an untrusted network.

When the dashboard starts, a daemon worker begins refreshing active app/keyword/storefront/device targets that do not have a successful check in the last 24 hours. The first run starts immediately and subsequent runs start every 24 hours while the process stays open. Recently checked targets are reported as skipped, failed and missing targets remain eligible, and overlapping automatic runs are prevented. The dashboard remains responsive, and the page polls local sync status and refreshes its visible rankings when a run completes. Apple still enforces its own rate limits, so large catalogs can take time to finish.

## Niche research

**Niche research** is an app-wide keyword workspace. It is intentionally independent from the apps in the left sidebar and does not use an app's rank history.

1. Open **Niche research**, describe the audience or product idea, and choose **Codex**, **Claude**, or **Auto-detect**.
2. **Brainstorm 10 keywords** asks the selected CLI for keyword phrases only. The local model never supplies volume, difficulty, or rank values.
3. The board creates one column for each selected storefront and runs the first public Apple search check automatically. Add or remove storefront columns at any time; the table scrolls horizontally as the board grows.
4. **Check now** refreshes every keyword/storefront pair. Cell values are the same transparent 0–100 ratings-based volume and difficulty estimates used elsewhere in the dashboard. A successful search with no public rating signals is shown as **No rated matches**, while an Apple request failure is shown as **Check failed**.
5. Use the right-hand agent input to request more phrases, such as `Add 5 beginner keywords`. New phrases are deduplicated, appended to the board, and checked across every board storefront automatically.

The discovery step invokes the locally installed `codex` or `claude` executable in non-interactive mode. Only the niche brief, existing keyword phrases, and your instruction are passed to that CLI. Authentication, account limits, and model usage belong to the local CLI you choose; the dashboard stores only the returned keyword phrases and the provider name in SQLite. If neither CLI is available, the provider is shown as unavailable and no remote fallback is used.

The optional agent settings in `config.toml` are:

```toml
agent_provider = "auto"
agent_timeout = 120.0
```

## Competitor keyword matrix

The Competitors tab starts with a keyword ranking matrix:

- The first column lists the primary app’s tracked keywords for the selected storefront and device.
- The remaining columns are the primary app plus every competitor added from a Top 5 app icon.
- Each cell shows a returned rank, `>limit` when the app was absent from Apple’s result window, `—` when that competitor has not yet been refreshed, or `!` when an Apple request failed.
- **Refresh rankings** performs one public Apple Search request per tracked keyword and extracts the primary and competitor positions from the same response.
- Competitor columns can be removed without deleting their locally stored rank data.

The app icon action menu is available from each Top 5 stack in the keyword rankings table. Adding a competitor does not add it to the left sidebar or to the primary tracked-app catalog.

## Apple Ads reporting

The **Paid search** tab is a read-only Apple Ads Platform API integration. It cannot create, pause, edit, or delete campaigns, ad groups, keywords, bids, or budgets.

Apple Ads requires a locally generated signed client secret. The app accepts the signed secret at:

```text
~/.local-aso-tracker/apple-ads-oauth/client-secret.jwt
```

For a custom `ASO_DATA_DIR`, place it at `<ASO_DATA_DIR>/apple-ads-oauth/client-secret.jwt`. The parent directory should be mode `0700` and the secret should be mode `0600`:

```bash
chmod 700 ~/.local-aso-tracker/apple-ads-oauth
chmod 600 ~/.local-aso-tracker/apple-ads-oauth/client-secret.jwt
```

The client ID is read from the signed JWT’s `sub` claim. OAuth access tokens remain in memory; the app never writes the client secret, OAuth token, or full Apple Ads response to SQLite, logs, exports, browser payloads, or Git. The client secret must be regenerated before its JWT expiry.

To connect:

1. Open an app and select **Paid search**.
2. Choose **Discover accounts** and select the Apple Ads ad account that owns the app campaigns.
3. Choose **Sync Apple Ads**. The app imports campaigns whose promoted app ID matches the selected App Store app.
4. Use the storefront and device selectors to view country/device-specific keyword metrics.

The 30-day report includes each keyword’s configured bid, match type, status, local spend, impressions, taps, tap installs, total installs, and cost per tap. The Paid search keyword table is grouped by the campaign’s Apple Ads country targeting rather than by campaign; a keyword used in multiple campaigns is aggregated into one country row with a campaign count. Paused keywords, including keywords in paused campaigns, are hidden by default and can be revealed with **Show paused**. Clicking an ASO Rank value refreshes that keyword/country/device ranking; a `⌕` value creates the missing local storefront and tracking target first. Keyword reports require one Apple Ads campaign query each, so larger accounts naturally take longer to synchronize. Apple Ads uses its own rate limits; the local client retries transient HTTP 429 and 5xx responses conservatively.

The suggestion section calls Apple’s read-only keyword-suggestion endpoint with the app ID, selected storefront, and up to 20 highest-ranking locally tracked ASO keywords. Apple’s returned popularity score is a relative suggestion signal and is not search volume. Suggested terms can be added to the local ASO tracker, but are never written back to Apple Ads.

## Local MCP server

While `aso dashboard` is running, connect a local MCP client to:

```text
http://127.0.0.1:8766/mcp
```

The server exposes read and controlled action tools backed by the same SQLite database:

- `list_apps` lists configured apps and App Store IDs.
- `list_storefronts` lists supported countries.
- `get_keyword_rankings` returns current ranks, estimate fields, and Top 5 competitors.
- `get_app_summary` returns visibility totals plus 7-day and 30-day changes.
- `get_listing_coverage` analyses saved title, subtitle, and keyword-field metadata.
- `add_app` adds or restores an app using Apple's public listing lookup.
- `add_keywords` adds keywords across storefronts and devices, with an optional automatic check.
- `run_checks` refreshes a bounded selection of active keyword targets.
- `stop_tracking_keywords` deactivates matching targets while retaining their history.

Action tools update the same SQLite database shown in the dashboard. `add_app`, `add_keywords`, and `run_checks` can contact Apple's public API. Bulk checks are capped at 50 keyword-market-device searches per call; split larger jobs into batches. History deletion is not exposed through MCP. The endpoint binds only to loopback. Dashboard and MCP start together; stop the dashboard process to stop both.

## CLI-only first setup

The dashboard is optional. To configure your own app entirely in the terminal, replace the example app name, numerical ID, and keyword with your values:

```bash
uv run aso init
uv run aso apps add --name "My App" --apple-id 123456789
uv run aso countries add us "United States"
uv run aso keywords add "daily journal"
uv run aso track add --app-id 123456789 --keyword "daily journal" --country us --device iphone
uv run aso check --app-id 123456789 --country us --device iphone
uv run aso rankings --app-id 123456789 --country us --device iphone
```

Unlike the dashboard’s keyword form, CLI catalog/target commands do not run a check automatically. Run `aso check` after adding targets. `aso init` alone creates an empty catalog; the dashboard creates the default storefronts when launched.

To try the included **AstroLingo demo catalog** instead:

```bash
uv run aso init --seed
uv run aso check --dry-run
uv run aso check
uv run aso rankings
```

`--seed` adds AstroLingo, five countries, 15 keywords, and 75 iPhone tracking targets. It is optional and safe to repeat. The dry run shows what would be checked without contacting Apple; the regular check fetches live public data. `track seed` is an idempotent convenience for rebuilding missing combinations after adding or reactivating catalog entries.

## What it measures—and what it does not

For every app/keyword/country/device target, the tracker calls:

```text
https://itunes.apple.com/search?term=...&country=...&entity=software&limit=200
```

iPhone targets use Apple’s public `software` entity. iPad targets use the separately documented `iPadSoftware` entity, so their rankings and history remain independent. Apple documents these entities and the 1–200 result limit in its [Search API reference](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).

It locates the app by numerical `trackId`; the one-based array position is saved as its rank. If the app is absent, the check stores `rank = NULL` and `found = false`, and the UI shows `>200`. This only means “not present in the retrieved result window.” It is not an asserted rank of 201.

This method approximates App Store search visibility. Country storefronts matter, and Apple may personalize, reorder, or experiment with results, so a specific device can differ. The Search API also sometimes returns fewer than the requested 200 results. The tracker stores Apple’s reported `resultCount` alongside the configured window.

The public Search API does **not** provide keyword search volume, downloads, or an official difficulty score. It does return app rating counts and average ratings, which the dashboard can use for transparent, reproducible estimates.

The public lookup API provides the localized app name, but it does not expose the App Store subtitle or keyword field. The coverage audit asks you to paste those two values from App Store Connect, stores them only in local SQLite, and never uploads them.

For each successful search, the tracker considers up to the first 10 returned apps:

- **Volume estimate (0–100)** is a position-weighted mean of `log1p(userRatingCount)`. Positions higher in Apple's relevance-ordered results carry more weight. The result is scaled to the 0–100 range and reduced when fewer than five matching apps expose ratings.
- **Difficulty estimate (0–100)** combines the weighted rating-count strength of matching apps, their average ratings, and the number of the first five results that expose ratings. A higher value indicates stronger rating signals among incumbents.
- These estimates are attached to the exact rank check that produced them in a separate `rank_estimates` table with a model version. Existing checks are not backfilled because the original result payloads are not retained.

The volume estimate is not Apple search volume and must not be interpreted as downloads. Difficulty is not an Apple score. Both depend on the public result window and rating data Apple returns. A result set with no exposed ratings produces `—` rather than a made-up zero or positive value.

## Storage and configuration

By default all mutable data stays under:

```text
~/.local-aso-tracker/
├── aso.db
├── config.toml
├── apple-ads-oauth/
│   └── client-secret.jwt
└── logs/aso.log
```

Checks store UTC timestamps; the CLI displays them in your local timezone. Browser dates follow your browser’s locale. Search keywords, storefronts, device entities, and app IDs are sent to Apple to retrieve public data. Apple Ads app IDs, account IDs, campaign IDs, keyword text, and report date ranges are sent to Apple only when the optional read-only integration is synchronized. Local history is not uploaded to a hosted ASO service.

Set `ASO_DATA_DIR` to use another directory. Keep the same value for every command in that workspace:

```bash
export ASO_DATA_DIR="$PWD/.local-aso-data"
uv run aso dashboard
```

In PowerShell:

```powershell
$env:ASO_DATA_DIR = Join-Path $PWD ".local-aso-data"
uv run aso dashboard
```

`config.toml` contains no secrets. Available settings are `request_timeout`, `retry_count`, `request_delay`, `concurrency`, `result_limit`, `agent_provider`, `agent_timeout`, `apple_ads_account_id`, `default_countries`, and `default_app_id`. Defaults are a 15-second timeout, three retries, at least one second between requests, concurrency 2, and a 200-result window. `apple_ads_account_id = 0` means that no ad account has been selected.

Example configuration:

```toml
request_timeout = 15.0
retry_count = 3
request_delay = 1.0
concurrency = 2
result_limit = 200
agent_provider = "auto"
agent_timeout = 120.0
apple_ads_account_id = 0
default_countries = ["us", "fr", "gb", "ca", "au"]
default_app_id = 6771773264
```

Catalog entries and tracking targets are managed with the dashboard or CLI, not by editing these defaults. Keep requests conservative; Apple can throttle searches or return fewer results. Restart the dashboard after changing configuration to apply it consistently.

Detailed diagnostics rotate locally in `logs/aso.log` (2 MB, three backups). Normal output stays concise. Put global flags before the command:

```bash
uv run aso --verbose check --country us
uv run aso --quiet check --only-missing-today
```

## Initialization

```bash
uv run aso init
uv run aso init --seed
```

Both forms are safe to run repeatedly. Migrations are applied with Alembic. The seeded app is AstroLingo (`6771773264`); storefronts are `us`, `fr`, `gb`, `ca`, and `au`.

## Apps

```bash
uv run aso apps list
uv run aso apps add --name "AstroLingo" --apple-id 6771773264
uv run aso apps add --name "Another App" --apple-id 123456789 --bundle-id com.example.app
uv run aso apps deactivate 6771773264
uv run aso apps activate 6771773264
uv run aso apps remove 6771773264
```

`remove` is intentionally a soft deletion (deactivation), preserving targets and history.

## Keywords

```bash
uv run aso keywords list
uv run aso keywords add "learn astrology"
uv run aso keywords add-file keywords.txt
uv run aso keywords deactivate "learn astrology"
uv run aso keywords activate "learn astrology"
uv run aso keywords remove "learn astrology"
```

Keyword files use one keyword per line. Blank lines and duplicates are ignored. Duplicate detection trims, collapses internal whitespace, and compares case-insensitively.

## Countries

```bash
uv run aso countries list
uv run aso countries add us "United States"
uv run aso countries deactivate us
uv run aso countries activate us
uv run aso countries remove us
```

Country codes must be two ASCII letters and are stored lowercase.

## Tracking targets

```bash
uv run aso track add --app-id 6771773264 --keyword "learn astrology" --country us
uv run aso track add --app-id 6771773264 --keyword "learn astrology" --country us --device ipad
uv run aso track remove --app-id 6771773264 --keyword "learn astrology" --country us
uv run aso track list
uv run aso track seed
```

An app, keyword, and country must exist before adding their target. Device defaults to `iphone`; supported values are `iphone` and `ipad`. Duplicate app/keyword/country/device combinations are prevented by the database. Removing a target deactivates it and preserves history.

## Rank checks

```bash
uv run aso check
uv run aso check --app-id 6771773264
uv run aso check --country us
uv run aso check --keyword "learn astrology"
uv run aso check --app-id 6771773264 --country us
uv run aso check --app-id 6771773264 --country us --device ipad
uv run aso check --only-missing-today
uv run aso check --concurrency 3
uv run aso check --dry-run
```

Each run groups targets by keyword, country, and device. Multiple tracked apps sharing that search use one Apple response. The same search is also cached within the process. One failed request does not stop other targets; retryable timeouts, connection errors, HTTP 429, and HTTP 5xx responses use exponential backoff with jitter. Validation and ordinary HTTP 4xx errors are not retried.

The command exits nonzero only when every attempted Apple search fails or a serious operational problem prevents the run.

## Rankings, history, and summary

```bash
uv run aso rankings
uv run aso rankings --app-id 6771773264 --country us --found-only --limit 25
uv run aso history --keyword "learn astrology" --country us
uv run aso history --keyword "learn astrology" --country us --days 30 --chart
uv run aso history --keyword "learn astrology" --country us --from 2026-07-01 --to 2026-07-31
uv run aso summary --country us --days 7
uv run aso summary --app-id 6771773264 --days 30
uv run aso opportunities --app-id 6771773264 --country us
```

Movement signs describe improvement: moving from 20 to 10 is `+10`; moving from 10 to 20 is `-10`. Entering the retrieved window is `NEW`, disappearing is `LOST`, and unchanged is `—`. The history chart labels its better direction explicitly. Summary averages exclude absent results rather than treating them as 201.

Opportunity groups use rank alone: defend (1–10), close wins (11–20), growth opportunities (21–50), weak visibility (51–100), very weak visibility (101–200), and not currently visible. The extra 101–200 group keeps returned results distinct from genuinely absent apps.

## Interactive local dashboard

Launch the dependency-free web dashboard:

```bash
uv run aso dashboard
uv run aso dashboard --no-open --port 8765
```

On a new installation, `uv sync` followed by `uv run aso dashboard` is enough. The dashboard initializes and migrates the local database, creates the default storefronts, and opens a three-step setup guide. Paste an App Store link or numerical app ID and choose a storefront, add your first keywords and device, then select the preferred local research agent. Ranking checks run automatically when those keywords are added. No account, API keys, sample apps, or sample keywords are required.

Setup completion is remembered in SQLite, and **Setup guide** in the sidebar reopens it anytime. Existing workspaces with apps are not interrupted by automatic onboarding.

The server binds to `127.0.0.1` by default and stops with `Ctrl+C`. It uses the same SQLite database and supports app/storefront switching, Apple-backed app import, comma/newline batch keyword entry, curated EN/FR/ES localization, multi-country and multi-device target creation, real iPhone/iPad filtering, running checks, filtering rankings, expandable rank history, listing-health review and competitor comparison. Submitting keywords automatically runs the first rank check for every selected keyword/storefront/device target; the manual check button remains available for later refreshes.

Localization is deterministic and runs locally. It supports a curated astrology vocabulary rather than calling a machine-translation service. Canada receives both English and French groups, while the US receives both English and Spanish groups. Uncurated phrases are still added to English markets and are skipped for non-English markets with a visible warning, which avoids silently posting English terms to local storefronts.

The visual design uses an app rail, compact app summary, tabbed work areas, rank tables, health breakdowns, and side-by-side comparison patterns inspired by modern ASO dashboards. It uses original Local ASO Tracker branding and no third-party frontend assets or framework.

Public Apple fields such as title, description, screenshot availability, ratings, release freshness, and localization count remain available as informational listing signals, but they do not contribute to the strategy score. Screenshot URLs are previewed when returned; otherwise the UI links to the App Store for manual verification and does not claim the listing lacks screenshots.

The numeric score remains hidden until the user saves a Keyword coverage audit and is then calculated only from that strategy audit. Up to 70 points come from avoiding repeated meaningful words across Name, Subtitle, and Keywords; each extra use reduces the repetition component by 15 points. Up to 30 points come from goal-specific title ordering. The audit ignores common connecting words and treats punctuation, accents, and case as non-distinguishing. Title ordering follows the selected strategy:

- **ASO / SEO / AEO:** one or more meaningful generic terms must precede the brand, and the brand should close the title.
- **UGC / Ads:** the brand must be the first meaningful term in the title.

The goal, brand term, and metadata are stored only in local SQLite for each app/storefront. The result remains a local heuristic rather than an Apple score.

Competitor comparison requires adding another app to the local catalog and compares only publicly returned listing fields.

The ranking table shows estimated audience and difficulty beside Apple's measured rank. Green volume values indicate the stronger end of the local audience model; red difficulty values indicate the strongest incumbent rating signals. Each successful check also stores the first five returned app names, Apple artwork URLs, average ratings, and rating counts. The icons appear as an overlapping stack with app-name tooltips, while the "Losing to" cards aggregate the most recent storefront-specific average rating and rating count for each competitor. The compact responsive row keeps rank, volume, difficulty, Top 5, and the existing opportunity signal visible without a horizontal scroll. These local estimates never replace Apple's returned rank and are never presented as measured search demand.


## Exports and report

```bash
uv run aso export csv --output exports/rankings.csv
uv run aso export history --output exports/history.csv
uv run aso export json --output exports/data.json
uv run aso report --output reports/aso-report.html
uv run aso report --output reports/aso-report.html --open
```

Missing directories are created. CSV uses UTF-8 with a BOM for reliable spreadsheet import. The HTML report is one self-contained file with embedded CSS, JavaScript, and data; after generation it needs neither a server nor an internet connection. It includes headline metrics, filters, current movement, opportunities, history, timestamp, and methodology.

Exports include local ranking data and should be treated as private unless you deliberately share them. Generated `reports/`, `exports/`, SQLite files, and environment files are excluded from Git by default. JSON is an export format; there is currently no JSON import command.

## Local scheduling

The tracker never installs a scheduler. Use the non-interactive idempotent command:

```bash
uv run aso --quiet check --only-missing-today
```

### macOS launchd

Copy `examples/launchd/com.local-aso-tracker.check.plist`, replace the absolute executable path, then opt in manually:

```bash
cp examples/launchd/com.local-aso-tracker.check.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.local-aso-tracker.check.plist
```

### Linux cron

Edit the absolute path in `examples/cron/local-aso-tracker.crontab`, then install it manually with `crontab examples/cron/local-aso-tracker.crontab`, or copy its line into `crontab -e`.

### Windows Task Scheduler

Edit and run `examples/windows/local-aso-tracker.ps1` from PowerShell. It registers a daily 09:00 task using the project virtual environment.

## Backup and restore

Stop the dashboard and wait for any CLI check to finish before making a file-copy backup. SQLite uses WAL mode: preserve the database with its `-wal` and `-shm` companions if they are present, or use SQLite’s backup command for a consistent standalone copy.

```bash
mkdir -p ~/Backups
sqlite3 ~/.local-aso-tracker/aso.db ".backup '$HOME/Backups/aso-backup.db'"
cp ~/.local-aso-tracker/config.toml ~/Backups/aso-config.toml
```

The backup command requires the `sqlite3` CLI. You can also use a SQLite tool’s backup function. For a custom `ASO_DATA_DIR`, substitute that path. Store backups outside the repository.

Restore with the app stopped: retain a backup of the current workspace first, then place the saved database and configuration in the application data directory. Do not leave another database’s WAL/SHM companions alongside the restored file. Run `uv run aso init` to apply newer migrations. Exports are useful for analysis, but do not replace a database backup for restoring tracking state.

## Updating an existing installation

Stop the dashboard, back up your database, then run these commands from the repository checkout:

```bash
git pull --ff-only
uv sync --locked
uv run aso init
uv run aso dashboard
```

Migrations are applied automatically on initialization and dashboard launch. Earlier development versions contained Apple Ads popularity and an ASO principle audit. Those specific obsolete tables remain removed by migration; apps, keywords, targets, and rank history are retained. The current paid-search integration is separate and read-only. Legacy `apple-ads.toml` credentials are not read; the current connector uses `apple-ads-oauth/client-secret.jwt`. Updating this app does not revoke external Apple access or modify campaigns.

## Troubleshooting

- **Database is not initialized:** run `uv run aso init` or `uv run aso init --seed`.
- **`uv` is not found:** install it using the official guide and reopen your terminal.
- **The browser cannot connect:** the dashboard process must still be running. Open the exact URL printed by the command.
- **Port 8765 is already in use:** stop the previous instance with `Ctrl+C`, or start with `--port 8766` and open the new URL.
- **No tracking targets:** seed them, or add the app, keyword, country, then `aso track add`.
- **Unknown app/keyword/country:** list the relevant catalog and add or reactivate it first.
- **Apple timeout/unavailable/429:** the client retries safe transient errors. Check the rotating log with `aso --verbose ...`; wait before increasing concurrency.
- **Malformed response:** Apple returned content outside the validated `resultCount`/`results` contract. The failure is stored without dumping the payload.
- **`>200` despite a device result:** the public API can differ from device search and may return fewer than 200 items.
- **Custom data location seems empty:** confirm that `ASO_DATA_DIR` is identical for initialization and later commands.
- **Screenshots are unavailable:** Apple sometimes omits screenshot URLs. Use the App Store verification link; unavailable media is not scored as zero.
- **No Apple Ads accounts found:** confirm that the signed client secret is unexpired, owner-readable only, and belongs to an Apple Ads user with API access.
- **Apple Ads empty for a market:** choose the correct storefront/device and run **Sync Apple Ads**; Apple returns only report rows with data for that completed-day window.

To discover command options:

```bash
uv run aso --help
uv run aso check --help
uv run aso track --help
```

## Development

```bash
uv sync --locked
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

The real Apple integration test is marked `integration` and skipped unless explicitly enabled:

```bash
ASO_RUN_INTEGRATION=1 uv run pytest -m integration
```

Migrations live in `migrations/`; application code is under `src/local_aso_tracker/`. Tests use temporary SQLite databases and mocked HTTP responses by default.

Run the project from its repository checkout as shown above. The source layout keeps responsibilities separate:

```text
src/local_aso_tracker/
├── cli.py                 # terminal commands
├── config.py              # local settings and paths
├── database.py            # SQLite sessions and migrations
├── models.py              # persistence models
├── apple/                 # public Apple HTTP client and validated responses
├── repositories/          # data access and onboarding persistence
├── services/              # rank checks, analytics, and listing health
├── reports/               # CSV/JSON exports and offline HTML generation
├── utils/                 # rotating local logs
└── web/                   # local HTTP server and packaged HTML/CSS/JavaScript
```

The dashboard assets are dependency-free and ship with the Python application. Do not add fabricated metrics or convert missing ranks into an asserted position outside Apple’s returned window. See [AGENTS.md](AGENTS.md) for contributor checks and architectural constraints.

## License

[MIT](LICENSE).
