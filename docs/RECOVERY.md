# Application recovery contract

## Phase 1 behavior

Studio preferences persist in SQLite transactions. The browser shows unsaved/saving/saved states and warns on leaving with an unsaved name. Edits only exist durably after the server acknowledges them. A browser closing before that acknowledgment can lose the unsaved edit.

Every preference update includes its expected revision; competing/stale edits are rejected. Reloading recovers the latest persisted value. Restart rotates the request token, so an open old tab must reload before saving.

Startup applies migrations and fails on an unknown future schema. Database errors do not trigger database recreation or deletion. File assets are resolved beneath the configured data root; source and data cannot overlap.

## Phase 2 library recovery

Characters, photos, labels, primary-photo choices and group membership survive restart. Revisions reject stale writes. Unsaved editor fields remain browser-only; save before leaving. Upload batches commit each photo separately and stop on the first failure. Reload to see what succeeded before retrying an uncertain response.

Before any photo bytes are written, generated paths enter a durable cleanup journal. Successful metadata commit removes those journal entries. After interruption, startup removes incomplete/uncommitted files. Photo/profile deletion commits cleanup records before removing files; locked-file cleanup remains queued and retries on restart. Active request cleanup only processes its own paths. Do not run multiple studio processes against the same data directory.

Archive/restore keeps references and memberships. Permanent deletion has no in-app undo; recover from a prior whole-folder backup. Deleting groups does not delete their characters. Missing files produce a visible backup-recovery error rather than deleting metadata. No operation resubmits generation requests.

## Phase 3 scene and engine recovery

Scenes, Base Images, analysis versions, prompt versions, engine settings and engine job records survive restart. A scene's workflow stage is derived from what is saved, so the scene reopens where it was left. Unsaved prompt or analysis edits stay in the browser only; the page warns before leaving.

Each engine run is recorded as `not_started` before anything launches; its job folder (`jobs/<scene>/analysis-<n>/` in the private data folder) is recorded before the CLI starts. If the studio stops during a run, the run becomes **Interrupted** at the next startup, and runs that had not started become **Cancelled** ("Nothing was sent"). Nothing is relaunched. An interrupted run may already have used plan allowance, or the CLI may have kept running after a hard stop; check its job folder before choosing "I checked — try again". Cancel and time limits stop the whole CLI process tree.

Scene creation and duplication use the same path-journal as photo uploads, so interrupted writes are cleaned at startup. Deleting a scene queues its original, thumbnail and job folder for deletion; locked files are retried at startup. Deletion is refused while a run is active.

## Phase 4 mapping and approval recovery

Subject assignments, the chosen group, selected reference photos, polish runs and approval snapshots survive restart. Approvals are never edited: an approval records its inputs (Base Image path and hash, analysis version and hash, subject boxes, prompt version, prompt and negative prompt, each subject's character and reference photo ids, hashes and image numbers). At startup and after every change the studio rebuilds that snapshot from the current data; any difference cancels the approval with a reason (`invalidated_at`, `invalidated_reason`) and keeps the record. Approving re-reads the Base Image and every chosen reference photo from disk and refuses if a file is missing or no longer matches its hash. Reference photos uploaded before Phase 4 get their hash once at startup.

A polish run is an engine job like an analysis (`jobs/<scene>/polish-<n>/`), with the same Interrupted and Cancelled handling. Its result is only a candidate stored with the job; the prompt changes only when the user chooses **Use polished**, so an interrupted or failed polish never alters a prompt. Deleting a character sets its subjects back to undecided; deleting a photo removes it from assignments. Both cancel affected approvals. Deleting a scene removes its assignments and approvals with it.

## Phase 5 generation and results recovery

Generation runs, manual export packages and results survive restart. A generation run is recorded as `not_started` with the approval it uses before anything launches; its folder (`jobs/<scene>/generation-<n>/`) and, as soon as Codex reports it, its thread id are recorded with the job. At startup a running generation becomes **Interrupted** and a waiting one **Cancelled** ("Nothing was sent"), like every engine run; nothing is resubmitted. A run that waited while its approval ended fails without sending anything.

An Interrupted, Cancelled or Failed generation may still have produced an image in Codex's own folder, so the studio offers **Look for a saved image**. It reads only that run's `generated_images/<thread_id>/` folder, keeps each image as a new result marked "recovered" and skips images already kept for that run. It never contacts OpenAI. Cancelling stops the local process; the request may already have used allowance.

Results are new files (`generations/<id>.<ext>` plus a metadata-free thumbnail) written with the same path journal as uploads, so an interrupted write is cleaned at startup. They are numbered per scene and never replaced. Each keeps the approval it was made from, so its exact inputs stay readable after later edits. Export packages (`jobs/<scene>/export-<n>/` with `package.zip`) keep their approval id; importing against a package links the result to that approval even if it has ended since. Deleting a result queues its files for deletion; deleting a scene deletes its results, packages and run folders. Deleting a character or photo whose copies sit in earlier packages asks whether to remove those copies too (never automatically); removal goes through the same deletion queue, and affected export zips are rebuilt afterwards.

## Phase 5.5 batch recovery

A batch (`batches` table) is a list of ordinary engine jobs sharing a `batch_id`, ordered by `batch_position`. Every item is persisted as `not_started` before anything launches, passes the same checks as a single click when queued (a valid approval per generation scene, no other run for the scene) and keeps its own job record, folder and results. The runner claims a batch item only while its batch's status is `running`; single clicks go first. The batch status records only the user's intent (`running`, `paused`, `cancelled`); progress is derived from its items.

At startup a running item becomes **Interrupted** like any run, waiting single runs are cancelled as before, but waiting batch items stay `not_started` and every running batch with items left is set to **paused** (reason "restart"). Nothing resumes until the user clicks Continue. A failure reported as usage limit, signed out or not installed pauses the item's batch and every other running batch on the same engine; a sign-in problem found before anything was sent puts the item back to `not_started`. Other failures mark only that item Failed. Cancel remaining marks waiting items Cancelled ("Nothing was sent") and never stops a run in progress. Try failed again creates new items (`retry_of` in the job settings), never reusing a failed record.

Group suggestions are stored as subject mappings whose `subjects_hash` is `suggested`; they never match the subjects fingerprint, so approval stays blocked until the user saves the assignments.

## Backups and restore

**Create backup** (Studio settings) writes `backups/character-studio-backup-<UTC time>.zip`. Consistency: inside one write transaction (`BEGIN IMMEDIATE`, so nothing commits meanwhile) the database is copied with SQLite's backup API through a separate read-only connection (WAL lets it read while the lock is held), and every file in the asset folders (`characters`, `scenes`, `generations`, `thumbnails`, `exports`, `jobs`) is hard-linked into a snapshot folder, or copied where links are not possible. The lock is then released and the zip is written from the snapshot, so files deleted afterwards are still included and the zip always matches its database. The manifest records format, schema revision, counts and each file's SHA-256 and size. An interrupted backup leaves only `*.partial` items, which are removed at the next start. Backups exclude the `backups` folder, logs, the launcher record and unmanaged folders.

**Restore** (`Restore-Studio.cmd`, studio stopped, or `python -m backend.backup restore [<zip>]`): the backup is unpacked into `<data folder>.restoring-<time>` with every file checked against the manifest (unsafe paths, unexpected or missing files and wrong hashes are refused), then the database passes `PRAGMA integrity_check` and its schema revision must be one this version knows. Only then is the current data folder renamed to `<data folder>.before-restore-<time>` and the restored folder renamed into place; if that fails, the original name is put back. The previous `backups` folder moves into the restored one. Nothing is deleted. On the next start the studio treats the restored data like any other: runs that were in progress become Interrupted and approvals are re-checked against the restored files.

For a manual copy instead, stop the studio and copy the **entire** data folder; never copy a running `studio.db` alone (the WAL file may hold committed changes).

## Mandatory later-phase implementation

- Done in Phase 5: generation and export call `backend.workflow.require_valid_approval` in the same transaction that records the job, and record the approval id with it.
- Persist generation jobs and attempts before dispatch. Keep pending/running/completed/failed/cancelled/interrupted/outcome_unknown distinct.
- An interrupted request that may have reached a provider becomes outcome_unknown; reconcile only through supported provider mechanisms.
- Never resubmit automatically after restart, timeout or an uncertain response. Provider idempotency and status lookup are capability-dependent, not assumed.
- A repeated generation needs explicit confirmation. Changed inputs require renewed approval. Local cancellation does not prove remote cancellation or absence of charges.
- CLI engine runs (D009: `claude -p` or `codex exec` analysis, `claude -p` polish, `codex exec` generation) persist their job record and job folder before launch. Statuses stay distinct: Failed (CLI error), Cancelled (user cancel), Interrupted (studio stopped mid-run). Job folders are kept for inspection; an Interrupted run may already have used allowance or saved an output, so the user checks its folder before retrying. Nothing is relaunched automatically.
- Keep exported manual (fallback) jobs waiting for user import, preserving package and approval identifiers. Imported results record user-supplied provenance honestly.
- Version outputs rather than overwriting. Character/reference deletion must offer explicit choices without silently corrupting history.
- Use atomic file writes, versioned asset keys and consistency-aware backups. Verify recovery with synthetic/authorized inputs.

## Phase 6A API engine recovery

API analyses are ordinary `analysis` engine jobs whose engine is `gemini_api`, `anthropic_api` or `openai_api`. The confirmed model is stored in the job's `settings_json` when it is queued and the reported token usage is added on completion. Restart handling is unchanged: a run in progress becomes Interrupted (its request may have reached the provider and been charged), waiting single runs are cancelled and waiting batch items stay until Continue. Continue and Try failed again on an API batch need the user's charge confirmation again. Keys live in `<data folder>/keys/` (Windows DPAPI, current user), outside backups. A restore moves that folder into the restored data folder. A key that cannot be decrypted (another Windows account or PC) reports "Enter it again" and nothing is sent.

Schema `0008_api_engines` rebuilds `engine_settings` and `scene_analyses` with the same rows. All migrations now run with `PRAGMA foreign_keys=OFF`, and `PRAGMA foreign_key_check` must return nothing before the upgrade commits.
