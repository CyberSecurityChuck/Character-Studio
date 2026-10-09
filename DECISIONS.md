# Architecture decisions

## D001 — Manual bridge first (2026-10-09)

- Decision: keep additional API costs at zero in the initial application; build provider contracts without network-backed AI implementations in Phase 1.
- Reason: user explicitly prioritizes avoiding additional API charges.
- Alternatives: separately billed image/vision APIs; unverified local model; subscription-backed analysis integration.
- Consequence: later MVP export/import is user-assisted. Codex chat tools are not assumed callable by FastAPI. Built-in usage still consumes plan allowances.
- Approval: explicit user preference and Phase 1 approval.

## D002 — Local modular monolith (2026-10-09)

- Decision: React/TypeScript/Vite, FastAPI/Pydantic, SQLAlchemy/Alembic with SQLite, local filesystem assets; one local service serves the built UI.
- Reason: matches PLAN.md; SQLAlchemy/Alembic support the specified relationships and migration requirements.
- Alternatives: PostgreSQL, microservices, Redis/Celery, desktop wrapper.
- Consequence: single-user, loopback-only application; add infrastructure only when demonstrated need warrants it.
- Approval: recommended in Phase 0 and included in approved Phase 1.

## D003 — Separate private storage and source (2026-10-09)

- Decision: configurable absolute data directory, default `%USERPROFILE%\Character-Studio-Data`; reject repository-contained or overlapping storage. Store asset paths relative to that root.
- Reason: private files must remain outside Git and survive source checkout changes. Launcher testing exposed Windows package redirection of LOCALAPPDATA; the user-profile path stays consistent between Codex and Explorer.
- Alternatives: repository-local data, absolute per-asset paths.
- Consequence: application-data backups are separate from Git checkpoints. Test data uses isolated temporary directories.
- Approval: PLAN.md requirement; default location is a Phase 1 implementation detail.

## D004 — Persistence and recovery boundaries (2026-10-09)

- Decision: versioned migrations and transactional settings now; schema/contracts for future approval and job workflows, with implementations deferred to their phases.
- Reason: verify durable foundations without prematurely implementing scenes or generation.
- Consequence: future jobs must persist before dispatch, support unknown outcomes, and never retry automatically; future approval snapshots must bind exact inputs.
- Approval: follows PLAN.md and the approved phase scope.

## D005 — Reproducible development and checkpoints (2026-10-09)

- Decision: uv-managed Python 3.12, project virtual environment and uv lockfile; npm lockfile; local Git milestone commits including continuity records.
- Reason: system Python launcher was not usable; a standalone runtime avoids dependence on Codex's bundled Python.
- Consequence: dependency installation needs network/cache access; normal startup does not download packages or call AI providers. No remote repository is configured.
- Approval: user approved Phase 1 dependency installation and Git checkpoint practices.

## D006 — Windows tooling compatibility and test client (2026-10-09)

- Decision: npm scripts call package JavaScript entrypoints with Node directly; use HTTPX2 for the installed Starlette test client.
- Reason: generated Windows npm command shims misparsed the ampersand in this project's directory. Starlette emitted a deprecation warning for its older HTTPX fallback.
- Alternatives: rename the user's directory; keep obsolete test-client dependencies.
- Consequence: no directory rename or global settings change; lockfiles capture installed versions. Package scripts and tests now pass.
- Approval: routine compatibility fixes within the approved Phase 1 implementation.
