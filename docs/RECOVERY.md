# Application recovery contract

## Phase 1 behavior

Studio preferences persist in SQLite transactions. The browser shows unsaved/saving/saved states and warns on leaving with an unsaved name. Edits only exist durably after the server acknowledges them. A browser closing before that acknowledgment can lose the unsaved edit.

Every preference update includes its expected revision; competing/stale edits are rejected. Reloading recovers the latest persisted value. Restart rotates the request token, so an open old tab must reload before saving.

Startup applies migrations and fails on an unknown future schema. Database errors do not trigger database recreation or deletion. File assets are resolved beneath the configured data root; source and data cannot overlap.

## Phase 2 library recovery

Characters, photos, labels, primary-photo choices and group membership survive restart. Revisions reject stale writes. Unsaved editor fields remain browser-only; save before leaving. Upload batches commit each photo separately and stop on the first failure. Reload to see what succeeded before retrying an uncertain response.

Before any photo bytes are written, generated paths enter a durable cleanup journal. Successful metadata commit removes those journal entries. After interruption, startup removes incomplete/uncommitted files. Photo/profile deletion commits cleanup records before removing files; locked-file cleanup remains queued and retries on restart. Active request cleanup only processes its own paths. Do not run multiple studio processes against the same data directory.

Archive/restore keeps references and memberships. Permanent deletion has no in-app undo; recover from a prior whole-folder backup. Deleting groups does not delete their characters. Missing files produce a visible backup-recovery error rather than deleting metadata. No operation resubmits generation requests.

## Backups at the current stage

No application backup/restore UI is implemented yet. For an offline manual backup, stop Character Studio, ensure its process has exited, then copy the **entire** private data directory to a separate backup location. Never copy only a running `studio.db`; active SQLite WAL files may contain committed changes. The baseline suite verifies SQLite's supported online backup primitive for the database.

To manually restore, stop the application, retain the current data directory as a separate recovery copy, restore the complete backup into a new external folder, point `STUDIO_DATA_DIR` there, and start. Verify preferences, character profiles, photos, groups and schema before using it. Do not overwrite your only copy. A full database-plus-assets consistent backup feature and restore test are required before the Phase 5 MVP is complete.

## Mandatory later-phase implementation

- Persist scenes, analyses, subject regions, mappings, selected references, draft/settings revisions, prompt versions and workflow stage alongside each feature.
- Preserve immutable approvals and exact input hashes. Restore approval only for unchanged inputs; changing inputs invalidates eligibility without erasing history.
- Persist generation jobs and attempts before dispatch. Keep pending/running/completed/failed/cancelled/interrupted/outcome_unknown distinct.
- An interrupted request that may have reached a provider becomes outcome_unknown; reconcile only through supported provider mechanisms.
- Never resubmit automatically after restart, timeout or an uncertain response. Provider idempotency and status lookup are capability-dependent, not assumed.
- A repeated generation needs explicit confirmation. Changed inputs require renewed approval. Local cancellation does not prove remote cancellation or absence of charges.
- Keep exported manual jobs waiting for user import, preserving package and approval identifiers. Imported results record user-supplied provenance honestly.
- Version outputs rather than overwriting. Character/reference deletion must offer explicit choices without silently corrupting history.
- Use atomic file writes, versioned asset keys and consistency-aware backups. Verify recovery with synthetic/authorized inputs.
