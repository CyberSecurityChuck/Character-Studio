# Changelog

## 2026-10-11 — Phase 5: Generation and Results (local commit, awaiting review)

- Approved by the user ("Approve Phase 5"). The scene workspace has a fifth step, Generate; approved scenes open on it. Stages "Generating…" and "Results ready" join the scene stages.
- Generate (Codex CLI): one run per click from a valid approval (`require_valid_approval` in the same transaction that queues the job, checked again when the run starts). The package comes from the approval snapshot and is hash-checked: numbered metadata-free JPEGs, prompt, negative prompt, a name-free mapping and the exact instruction. Codex is run with the Phase 2.5 flags (read-only sandbox, `--ephemeral`, `--ignore-user-config`, `-i` per image, `-o`, `--json`). Success only when the final message names an existing image inside this run's `generated_images/<thread_id>/` folder. Progress, Cancel, time limit, clear errors (not installed, signed out, usage limit, time limit, no image), no retry.
- Generate again and Variation ask for confirmation and add new results; a variation adds one fixed line asking for small natural differences. Results are never overwritten.
- Recovery: a failed, cancelled or interrupted generation offers "Look for a saved image", which checks only that run's Codex folder and keeps what it finds as a "recovered" result (no duplicates). Codex's thread id is recorded with the job.
- Manual bridge: Export for manual use builds the same package with a README and downloadable zip (names in `mapping.txt` because the user handles it); Import result links an image made elsewhere to its package or the current approval, with an optional "Made with" note.
- Results: per-scene grid and a Results page (search, Preferred only), Overview "Latest results", a viewer with Result / Side by side / Slider comparison, the inputs it was made from, Mark as preferred (one per scene), Download and Delete. Deleting a scene deletes its results.
- Schema `0006_generation` (additive: `generation_results`; `engine_jobs.settings_json`, `engine_jobs.provider_request_id`). Providers: Codex and the manual bridge now list generation; the paid OpenAI API adapter stays disabled (needs separate approval, D009).
- 9 new tests (91 total); one foundation test updated for the generation providers. No dependencies added. See D016.

## 2026-10-11 — Phase 4 accepted

- The user's follow-up check passed after the comparison fix ("Phase 4 accepted"). Phase 4 is complete. Status, handoff and user guide updated; `main` pushed to the private GitHub repository with the user's approval (CI not run). Phase 5 needs "Approve Phase 5".

## 2026-10-11 — Phase 4 review fixes (local commit, awaiting follow-up check)

- From the user's Phase 4 review (34/34 steps, "Needs fixes first"). Approved with "Yes, please go ahead with all four fixes".
- Subject box labels no longer lose their first letters in Adjust subjects: a leftover Phase 3 style rule positioned every element inside a box, including the avatar and the resize handle.
- Subject boxes can now be resized from any side or corner: eight handles on the selected box with larger grab areas, a box is selected when Adjust subjects opens, and the help text explains moving and resizing (Shift + arrow keys on the keyboard).
- The required-element check now also needs the instruction that each subject's identity comes only from its own images; listing the attached images is no longer enough. Polish is told to keep it.
- Prompt versions can be deleted from a new Version history window (list, preview, Load into editor, Delete version). The approved version and a version being polished cannot be deleted; version numbers recorded by approvals are never reused.
- From the follow-up check (13/13; step 5 flagged): the polish comparison now marks changes in long prompts. It compares lines first, then words only inside changed passages, ignores line wrapping, and shows how many words were removed and added. Verified with a 3,671-word prompt.
- No schema change. 82 tests pass (1 new, 1 extended).

## 2026-10-11 — Phase 4: Character Mapping and Approval (local commit, awaiting review)

- Approved by the user ("Approve Phase 4"). The scene workspace is now four steps: Analysis, Characters, Prompt, Review, kept in the address so a refresh keeps the step.
- Characters: per subject, Use a character / Keep original / Decide later; one character per subject per scene; group filter that never assigns anyone; automatic reference photo choice (primary, closest view to the face angle, then distinct views; up to 3) or manual choice (up to 4, ordered); image numbers shown on the photos. Subject boxes can be moved, resized, added and removed (new analysis version; labels never renumber). A fresh analysis asks the user to re-check assignments.
- Prompt: the template names each subject's identity images and keep-original subjects; character names never enter the prompt; "Rebuild with the assignments" when assignments change. Required-element check (each subject linked to its image numbers, keep-original instructions, no image numbers beyond those attached).
- Polish prompt (Claude, text only, no tools): progress, Cancel, clear errors, no retry; side-by-side comparison with word-level highlights; Use polished / Keep original / Edit by hand; missing elements need explicit acceptance; both versions kept with the polished flag.
- Review and approval: everything the image will be made from, blockers and warnings, cost and engine notes; immutable approval snapshots with content hashes, verified against the files on disk; automatic cancellation with a reason when any input changes (also on photo or character deletion, and after restart); withdraw; approval history. `workflow.require_valid_approval` is the gate Phase 5 must use.
- Library: delete confirmations explain the effect on scenes; deleting a character makes its subjects undecided; deleting a photo removes it from assignments.
- Schema `0005_mapping` (additive). 12 new tests (81 total). No dependencies added. See D014.

## 2026-10-11 — Phase 3 accepted

- The user's follow-up check passed (17/17, 0 problems, "Phase 3 looks good"). Phase 3 is complete. README, status and handoff updated; `main` pushed to the private GitHub repository with the user's approval (CI not run, by the user's choice). Phase 4 needs "Approve Phase 4".

## 2026-10-11 — Phase 3 review refinements (local commit, awaiting follow-up check)

- From the user's Phase 3 review: ⋯ card menus and a Select mode on Scenes (Rename, Duplicate, Delete; bulk Delete), Characters (Rename, Archive/Restore, Delete; bulk Archive/Restore/Delete) and Groups (Rename, Delete; bulk Delete), with a shared rename dialog.
- Studio settings explanations moved into ⓘ tips (generation engine, time limits, analysis engine choices).
- Analysis text is shown in sentence case (display only; stored analyses unchanged).
- Cancel shows "Stopping…" immediately and disables itself until the run ends.
- The "Your groups" and "No groups yet" panels now match in height. Select is hidden when a list is empty.
- Frontend only; no API, schema or dependency changes. 69 tests pass.

## 2026-10-10 — Phase 3: Scene Analysis (local commit, awaiting review)

- Approved by the user ("Approve Phase 3"). Scenes: Base Image upload, thumbnails, rename, duplicate, delete, resume and recent scenes on the Overview.
- Analysis through the Claude Code CLI (default) or Codex CLI, or the manual copy-and-paste fallback, all validated by one schema and saved as versions with source, CLI version and raw output. Uncertain details can be confirmed or corrected; edits become new versions.
- Studio prompt template with numbered images, "Subject N" labels, identity/composition locks, negative prompt and optional scene changes; saved and restorable prompt versions.
- Queue-ready engine job runner (one job at a time), per-run job folders with a metadata-free Base Image copy, timeout, Cancel, clear errors with "Try again"/"Do it manually", no automatic retry, Interrupted/Cancelled reconciliation at startup.
- Studio settings: engine status with "Check again", analysis and generation engine choice, per-engine time limits.
- Schema `0004_scenes`. 20 new tests with a fake CLI (69 total). No dependencies added. See D012.

## 2026-10-10 — Prepared for public GitHub release

- Rewrote the local (never pushed) history with the user's approval: noreply author/committer email on all commits; local Windows profile path replaced with `%USERPROFILE%`. Backup branch kept locally.
- Added a public README with badges, Mermaid workflow/architecture/roadmap diagrams and screenshots of fictional demo characters. Moved the operator README to `docs/USER_GUIDE.md` and updated its references (AGENTS.md, Setup.ps1, continuity test).
- Added MIT `LICENSE`, `RESPONSIBLE_USE.md`, `SECURITY.md` and a GitHub Actions workflow (Windows tests, lint and build, plus a privacy guard). `.gitignore` now allows only `docs/images/*.png` screenshots and ignores local browser-automation output.

## 2026-10-10 — Phase 2.5 engine verification spike

- Ran the approved spike with throwaway tests only; no application code changed. Confirmed versions, sign-in and real flags for `claude` 2.1.296 and `codex-cli` 0.162.1.
- Claude and Codex analysis both returned schema-valid JSON (49 s / 52 s) and were confined to their job folders (`--restricted`; Codex `-s read-only` blocks commands).
- Codex generation with two consenting reference photos produced an image in 72 s at `~\.codex\generated_images\<thread_id>\`; the user judged the likeness "clearly me".
- Recorded failure appearances (signed out, timeout, no image produced, which exits 0) and implementation notes in `docs/PROVIDER_FINDINGS.md`. The official OpenAI docs do not promise identity preservation.

## 2026-10-10 — Batch processing planned (planning only)

- Recorded D010: Phases 3–5 use a queue-ready job runner (single job per click); new Phase 5.5 adds batch scene creation, batch analysis, batch generation of individually approved scenes, N variations and optional quick group mapping. Moved "Batch generation" and "Multiple image variations" out of Phase 6. Added `batch_id`/`not_started` to the planned GenerationJob model. No application code changed.

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
