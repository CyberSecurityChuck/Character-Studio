# Architecture decisions

## D001 — Manual bridge first (2026-10-09)

- Decision: keep additional API costs at zero in the initial application; build provider contracts without network-backed AI implementations in Phase 1.
- Reason: user explicitly prioritizes avoiding additional API charges.
- Alternatives: separately billed image/vision APIs; unverified local model; subscription-backed analysis integration.
- Consequence: later MVP export/import is user-assisted. Codex chat tools are not assumed callable by FastAPI. Built-in usage still consumes plan allowances.
- Approval: explicit user preference and Phase 1 approval.
- Status (2026-10-10): superseded as the main approach by D009. The manual flow (copy instruction, export package, import result) is retained as the fallback.

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

## D007 — Local Character Library and file consistency (2026-10-09)

- Decision: add Phase 2 with one additive Alembic migration, generated asset keys, unchanged originals, metadata-free thumbnails, bounded raw-body uploads and no new dependencies.
- Reason: build the approved local library while keeping personal images outside source and avoiding AI charges. Raw image uploads avoid an extra multipart dependency and temporary spool files.
- Decision: serialize writes before reading revisions. Journal upload paths before writing and clear the journal in the metadata transaction; queue deletions transactionally and retry unfinished cleanup on startup.
- Consequence: only committed references are served. Failed batches retain earlier successful photos. An uncertain browser response requires reload before retry; no automatic resubmission. Single local service per data directory remains the operating model.
- Decision: archive is reversible and retains memberships/photos; permanent deletion is explicit. There is currently no generation history. Later history must restrict referenced deletion or preserve immutable snapshots, never cascade history away.
- Approval: explicit "Approve Phase 2"; Phase 3 and AI operations remain unapproved.

## D008 — Phase 2 review refinements (2026-10-10)

- Decision: store avatar framing per reference photo as display metadata (focus point x/y in 0–1 and zoom 1–4) via additive migration `0003_photo_framing`; render it with CSS percentages so one frame matches every avatar size.
- Reason: the user wanted to choose the visible area of round thumbnails. Re-cropping files would alter or duplicate private images; metadata keeps originals and stored thumbnails unchanged.
- Alternatives: server-side cropped avatar files; a single per-character crop (lost when the primary photo changes).
- Decision: hash routes plus `history.replaceState` preserve the current page, library tab and open profile/group across browser refresh, with no backend fallback route and no new history entries.
- Alternatives: path routes (needed a server SPA fallback and restart); pushState history (needed Back-button unsaved-edit guards).
- Decision: short single-purpose forms (group editor) use a footer action bar (destructive left; Cancel/primary right). The long, multi-section character profile keeps Close at top-right so leaving never requires scrolling past Archive/Delete.
- Decision: the user's local review checklists/reports in `Phase_Checks/` stay out of Git (`.gitignore`).
- Approval: user-requested Phase 2 review changes on 2026-10-10 within the approved Phase 2 scope; Phase 3 and AI operations remain unapproved. No dependencies added.

## D009 — CLI bridge first, manual bridge as fallback (2026-10-10)

- Decision: the studio remains the only screen the user works in. Instead of the user carrying files and text to other apps, the studio runs the official command-line tools installed and signed in on this PC, in the background, one user-initiated run at a time:
  - Scene analysis: Claude Code CLI (`claude -p`) on the user's Claude Pro subscription.
  - Optional "Polish prompt": Claude Code CLI on the user's Claude Pro subscription.
  - Image generation: Codex CLI (`codex exec` with its built-in image generation) on the user's ChatGPT subscription.
  - The D001 manual bridge (copy instruction, export package, import result) remains as the fallback, not the main path.
- Replaces D001 as the main approach; D001's manual flow is kept as the fallback for every engine step.
- Reason: stop switching between apps. Both CLIs run on existing subscriptions with no API keys and no per-use billing. Each run still consumes that plan's usage allowance.
- Split: Claude for analysis and prompt polishing, Codex for images only, so the ChatGPT image allowance is spent on images.
- Boundaries: only the official `claude` and `codex` programs, run locally for the user's personal use, signed in by the user. The studio never reads, copies, stores or forwards their login tokens. No extracting subscription credentials into other tools, no third-party gateways (for example OmniRoute), no browser automation or scripting against chatgpt.com or claude.ai. User-supplied findings: Anthropic allows subscription logins only inside Claude Code and Claude.ai; scripted website use breaks OpenAI's terms. See `docs/PROVIDER_FINDINGS.md`.
- Every run is started by an explicit user action (Analyse, Polish prompt, Generate from a valid approval). Never retried automatically; interrupted runs are marked failed/interrupted and not resubmitted.
- Alternatives: manual bridge only (D001; too much app switching); paid OpenAI/Anthropic APIs (per-use billing); third-party subscription gateways or website automation (violate provider terms; rejected).
- Open risk: it is not yet confirmed in practice that Codex's built-in image tool uses attached local reference photos to keep each person's likeness. Phase 2.5 (engine verification spike) records the CLI flags, output locations, timings and failure modes, plus the user's likeness judgement, before Phase 5's Generate button is built on it. The user has stated that OpenAI's documentation confirms reference-photo/identity support, so likeness quality is recorded as a quality check rather than a gate; the manual bridge stays as the fallback either way.
- The optional paid OpenAI API adapter (PLAN.md §12.3) stays off and unchanged.
- Approval: user-directed planning change on 2026-10-10. Planning documents only; no application code changed. Phase 2.5 and Phase 3 require explicit approval ("Approve Phase 2.5").
