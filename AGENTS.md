# Local ASO Tracker contributor instructions

- Target Python 3.12 or newer and manage the environment with `uv`.
- Keep the application local-only. Persist application data in SQLite and make external runtime requests only to Apple's public iTunes Search API.
- Keep CLI, configuration, persistence, Apple HTTP code, services, and report generation in separate modules.
- Use UTC for persisted timestamps and local time for user-facing CLI timestamps.
- Preserve ranking uncertainty: a missing app has `rank = NULL`, `found = false`, and is displayed as `>limit`.
- Never invent search volume, downloads, keyword difficulty, or an exact rank beyond Apple's returned result window.
- Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, and `uv run pytest` before declaring work complete.
- Automated tests must mock Apple. The live integration test must remain opt-in.
- Migrations are the source of truth for schema creation. `aso init` must be idempotent.
- Do not log full Apple response payloads.
- The dashboard must stay local, use original Local ASO Tracker branding, and never display invented popularity, difficulty, download, or volume metrics.
- Keep dashboard assets dependency-free and package them with the Python application; no frontend build pipeline is required.
