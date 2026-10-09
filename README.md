# Character Studio

A local-first home for reusable characters, reference scenes and approved image workflows.

**Current scope: Phase 1 foundation.** The working application has an overview, local connection status, persistent studio-name settings, external data storage and a truthful provider status screen. Character uploads, scenes, analysis, approvals, generation and export/import are not implemented yet. PLAN.md defines those later phases. Do not upload personal photographs into the source folder.

## Start and stop

After setup, double-click **Start-Studio.cmd**. It starts the local service in the background and opens **http://127.0.0.1:8765**. Double-click **Stop-Studio.cmd** to stop the launcher-managed service. Closing the browser does not stop the service. Save changes before closing; only changes acknowledged as saved are durable.

The launcher refuses to stop a process whose executable/start time no longer matches its record. For terminal development, use `uv run --locked python -m backend` and Ctrl+C instead.

## First setup / clean checkout

Prerequisites: Windows, Node.js 24 LTS with npm, and uv. Python 3.12 is managed by uv; dependencies live in the project's `.venv`. No OpenAI account credentials or API key are required by this application.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1
```

Setup installs locked Python and npm dependencies and builds the frontend. Package downloads require internet access. Normal startup requires neither downloads nor AI requests. Do not modify lockfiles without recording the dependency change.

Equivalent commands:

```powershell
uv sync --locked --python 3.12
npm.cmd ci --prefix frontend
npm.cmd --prefix frontend run build
uv run --locked python -m backend
```

## Storage and configuration

Default data directory: `%USERPROFILE%\Character-Studio-Data`. The application creates `studio.db` plus directories for characters, scenes, generations, thumbnails, exports and backups. Only studio preferences are stored in Phase 1. These files belong to the user and must survive source updates. The user-profile location avoids Windows packaged-app redirection of `LOCALAPPDATA`, so launches from Codex and Explorer use the same default.

Optional environment variables, set before starting:

```powershell
$env:STUDIO_DATA_DIR = 'D:\Character-Studio-Data'
$env:STUDIO_PORT = '8765'
```

`STUDIO_DATA_DIR` must be absolute and outside (and not a parent of) the source repository. Changing it opens a different data directory; it does not move existing work. Stop the running service before changing configuration. Use the same environment configuration when stopping it. Do not put the live SQLite database in a shared/network/cloud-sync folder.

The backend always binds to `127.0.0.1`. Host/origin checks, a per-process request token, CSP and no-store responses restrict browser-based misuse. This is a single-user local tool, not a public authenticated service. Local files are not encrypted; anyone with filesystem access can read them. No analytics, remote fonts or AI network clients are included.

## Development

Backend: `uv run --locked python -m backend`.

Frontend in a separate terminal: `npm.cmd --prefix frontend run dev`, then visit `http://127.0.0.1:5173`. Vite proxies `/api` to the local backend. Set the same `STUDIO_PORT` for both processes if changing it. After frontend changes, build again for the normal launcher.

```powershell
uv run --locked pytest
uv run --locked ruff check .
npm.cmd --prefix frontend run build
```

If a restricted agent sandbox prevents uv cache access, use the installed executables for offline checks: `.\.venv\Scripts\python.exe -m pytest` and `.\.venv\Scripts\ruff.exe check .`. An agent should request appropriate escalation for necessary blocked operations rather than change system permissions.

Tests use isolated temporary data outside the repository. They do not call external image services. The database schema is managed by Alembic on startup; unknown future revisions fail rather than being downgraded. Never edit historical migrations after release; add a new revision. Migrations receive an explicit SQLAlchemy connection from `backend/persistence.py`; destructive downgrades are disabled.

## AI capabilities and costs

Phase 1 includes interfaces and capability metadata only. Manual bridge is **planned**, direct Codex generation is **unverified**, and paid OpenAI API access is **disabled**. There is no generation endpoint, credential storage or automatic retry behavior. An installed Codex image tool is not a callable FastAPI provider.

The intended MVP lets the user export an approved package to Codex/ChatGPT and import the result. External generation consumes the external service's plan allowances and sends supplied images to that service. There is no promise of unlimited generation or perfect likeness/pose preservation. See `docs/PROVIDER_FINDINGS.md`.

## Continuity and recovery

- Open a new Codex conversation **in this project folder** and say **Resume Character Studio**.
- Read AGENTS.md, PLAN.md, PROJECT_STATUS.md and SESSION_HANDOFF.md; compare them with actual Git/files before continuing.
- Say **Checkpoint Character Studio** before a planned pause. See `docs/CONTINUITY.md` for the exact protocol.
- Approval covers Phase 1 only. Development must stop before Phase 2 until explicitly approved.

For data recovery and current backup limitations see `docs/RECOVERY.md`. Git backs up source history, not private application data.

## Troubleshooting

- **Cannot reach studio:** run Start-Studio.cmd; check `server.stderr.log` in the selected private data folder. No request bodies are logged.
- **Port in use:** stop the existing instance or select another port; do not kill unrelated services.
- **Session expired after restart:** reload before saving; the per-process request token has changed.
- **Another tab saved first:** the app rejects the stale save and retains your typed edit. Copy it before choosing "Discard local edit and reload".
- **Database revision error:** stop and inspect the error; preserve the data folder. Do not delete or downgrade the database to fix startup.
- **Build missing:** run `npm.cmd --prefix frontend run build`, then restart.
