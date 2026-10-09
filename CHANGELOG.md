# Changelog

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
