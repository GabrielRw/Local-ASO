# Local ASO Tracker contributor instructions

- Target Python 3.12 or newer and manage the environment with `uv`.
- Keep the application local-only. Persist application data in SQLite and make external runtime requests only to Apple's public iTunes Search API, the optional read-only Apple Ads Platform API, and the optional App Store Connect API using local credentials. The only other HTTP target allowed is the user's own Ollama on a loopback address. Local AI CLIs (Claude, Codex, Gemini, OpenCode) are run as subprocesses; the app itself never calls an AI service.
- Every dashboard POST must pass the origin check (loopback Host, JSON body, matching Origin when sent). Server actions that write files only write inside `config.exports_dir()`.
- Keep CLI, configuration, persistence, Apple HTTP code, services, and report generation in separate modules.
- Use UTC for persisted timestamps and local time for user-facing CLI timestamps.
- Preserve ranking uncertainty: a missing app has `rank = NULL`, `found = false`, and is displayed as `>limit`.
- Never invent search volume, downloads, keyword difficulty, or an exact rank beyond Apple's returned result window.
- Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, and `uv run pytest` before declaring work complete. When `frontend/` changed, also run `pnpm --dir frontend typecheck`, `pnpm --dir frontend lint`, `pnpm --dir frontend test`, and `pnpm --dir frontend build`. When `desktop/` changed, run `cargo check` in `desktop/src-tauri`.
- Automated tests must mock Apple. The live integration test must remain opt-in.
- Migrations are the source of truth for schema creation. `aso init` must be idempotent.
- Do not log full Apple response payloads.
- The dashboard must stay local, use original Local ASO Tracker branding, and never display invented popularity, difficulty, download, or volume metrics.
- The dashboard is a React + TypeScript + Tailwind + shadcn/ui app in `frontend/`. Its production build goes to `src/local_aso_tracker/web/static/` and is committed, so `uv run aso dashboard` works from a checkout without Node. Rebuild (`pnpm --dir frontend build`) and commit the output whenever `frontend/` changes.
- The built dashboard must satisfy the server CSP: no inline scripts, no third-party hosts except Apple artwork (`*.mzstatic.com`), fonts bundled locally.
- Product display rules live in `frontend/src/lib/format.ts` (`rankLabel`, `demand`): a missing rank reads `>limit`, local estimates carry `~`, Apple's popularity floor (5) reads "Low". Views must use these helpers.
- The macOS app in `desktop/` (Tauri 2) only launches the bundled server (`aso dashboard --no-open --no-mcp --port 0`), waits for its `LOCAL_ASO_READY <url>` line, and opens that URL; keep that contract, SIGTERM shutdown, and packaged migrations (`src/local_aso_tracker/migrations/`) working. Build with `scripts/build-macos.sh`.
