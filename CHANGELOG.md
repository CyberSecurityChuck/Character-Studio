# Changelog

## 2026-10-10 — Plan v2.1 conflicts resolved (planning only)

- Recorded the user's answers on the eight v2.1 open questions in D009 and PLAN.md: mechanics-only spike gate; cite the OpenAI identity-support page in the spike; both Claude and Codex analysis engines in Phase 3; approval covers content, not the engine; distinct Failed/Cancelled/Interrupted statuses; GPS stripping for analysis copies; consistent Polish prompt error handling; folder confinement where supported.
- Planned post-MVP paid API engines for analysis and generation (off by default, separate approval, per-run cost confirmation). AGENTS.md now cites D009 and this boundary.
- Updated README, PROVIDER_FINDINGS (new spike rows) and RECOVERY. No application code changed.

## 2026-10-10 — Plan v2.1: CLI bridge first (planning only)

- Recorded D009 "CLI bridge first, manual bridge as fallback": Claude Code CLI for scene analysis and optional prompt polishing, Codex CLI for image generation, manual bridge as fallback. D001 marked superseded as the main approach.
- PLAN.md v2.1: new Phase 2.5 engine verification spike; Phase 3 Analyse button, job folders, analysis UI and engine settings; Phase 4 optional Polish prompt; Phase 5 Generate via Codex; §8.3, §12, §20, §22 and §27 updated.
- README, `docs/PROVIDER_FINDINGS.md` (subscription-use findings and spike placeholder) and `docs/RECOVERY.md` (CLI job recovery) updated. No application code, dependencies or phase completion status changed.

## 2026-10-10 — Phase 2 review refinements

- Addressed the user's hands-on Phase 2 review (local `Phase_Checks/` checklist and report, excluded from Git).
- Character cards and profile header use round avatars. Added per-photo thumbnail framing (drag/zoom editor with live previews); originals are untouched. Migration `0003_photo_framing` adds three display-only columns with defaults for existing photos.
- Profile editor: Name/Age side by side, compact photo cards (Primary badge, label + size row, side-by-side actions), styled Add photos button, group chips that open the group.
- Groups: single primary "+ New group" in the list header; "Select a group" placeholder matches the list height; editor actions moved to a footer (Delete left, Cancel/Save right); creating a group closes the editor; member avatars in rows and picker; "1 member" pluralization.
- Sidebar icons for Characters, Scenes and Results; "Show archived" aligned with the filter row.
- Browser refresh keeps the current page, tab and open profile/group via hash routes (`#/characters/<id>`, `#/groups/<id>`, `#/settings`) without adding history entries.
- Fixed the preview-dialog image rule shrinking the framing editor image.
- Verified 49 tests (new: framing update/validation and 0002→0003 upgrade with existing photos), Ruff and production build; browser-tested on an isolated synthetic data folder (port 8766). The user's studio was restarted and is on `0003_photo_framing`.

## 2026-10-09 — Phase 2 Character Library

- Recorded explicit Phase 2 approval; Phase 3 and later remain gated.
- Added persistent character profiles, multiple reference photos, labels, primary selection, thumbnails, preview, name search and reusable groups/memberships.
- Added archive/restore, explicit deletion choices, optimistic revision checks and durable file cleanup for interrupted uploads/deletions.
- Added migration `0002_library`, preserving studio preferences. Original photos remain unchanged and external; thumbnails exclude source metadata.
- Verified 47 tests, Ruff and frontend production build; browser tested creation/upload/labels/primary/preview/groups and actual stop/start recovery using isolated synthetic data.
- Verified the fresh-conversation development recovery exercise. No paid calls, dependency additions, remote setup or publishing.

## 2026-10-09 — Phase 1 foundation

- Added the React/TypeScript studio overview and settings with honest planned-provider statuses.
- Added FastAPI, SQLite with Alembic migration `0001_foundation`, transactional studio preferences and optimistic revision checks.
- Added configurable external data storage, traversal/overlap validation and local host/origin/session-token safeguards.
- Established analysis/generation contracts and job-state vocabulary; no provider execution or paid operations are implemented.
- Added standalone uv-managed Python environment and locked Python/npm dependencies.
- Added Windows setup/start/stop launchers; resolved the npm shim issue caused by the ampersand in the project path.
- Changed the planned default data location to the user-profile directory after live testing exposed Windows packaged-app LocalAppData redirection.
- Created all mandatory continuity records, dated provider findings and development/application recovery procedures. PLAN.md remains unchanged.
- Verified 29 automated tests, clean Ruff lint, TypeScript/Vite production build, browser preference save, launcher stop/start and restored saved state.
- Audited continuity dependencies and Git privacy exclusions. Actual fresh-conversation recovery exercise is documented but not yet performed.
- Resumed after a usage-limit interruption, reconciled uncommitted work and reran 29 tests, lint and build successfully before completing the local checkpoint.
