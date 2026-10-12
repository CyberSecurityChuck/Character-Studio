# Changelog

## 2026-10-12 — README screenshots and repository settings

- Four new README screenshots (Characters step, comparison slider, Edit area, engine settings) from a throwaway demo studio with fictional characters and scenes drawn as simple illustrations; no real people and no AI-generated images.
- Wording: "Add your … key" instead of "Add a OpenAI API key" in engine and edit messages.
- Repository (with the user's approval): public; secret scanning, push protection, private vulnerability reporting and Dependabot security updates enabled.

## 2026-10-12 — Phase 6 complete; docs ready for a public repository

- The user's follow-up check passed (`Phase_Checks/Phase6CD_Followup_Report.md`: 16/16 steps, 0 problems, "Phase 6C and 6D look good"). 6C-1, 6C-2 and 6D are accepted, so every phase in PLAN.md is complete. Both success styles (toast and green inline confirmation) stay for now.
- GitHub-facing docs updated for Phases 1–6: README (status, features, how the AI part works with the optional API engines, architecture, privacy, roadmap, tech stack, CI), USER_GUIDE (scope, keys and masks folders, AI capabilities, confirmations), SECURITY (API keys, protected backups, new scope items), RESPONSIBLE_USE (all providers, Replace a person), DESIGN (Phases 5–6), AGENTS and the PLAN.md status header (requirements unchanged).
- CI now runs on every push to `main` and every pull request (and by hand), since the repository is becoming public.

## 2026-10-12 — Phase 6C + 6D review fixes

- From the user's combined review (D029). **Edit area** stays off for results whose approval you withdrew, but the viewer now says so plainly and how to get an editable result (a result from the current approval, or a free **Import result**).
- **Success messages** are now easy to see everywhere: a toast in the top-right corner (green check, title, detail, closes itself after about 5 seconds) plus a green confirmation in the panel (green banner, or a green "Saved to this computer" badge next to Save). Test key, key saved, engine and studio-name saves, presets, backups, scene and library actions all use it. New `frontend/src/Toast.tsx`. No backend changes.

## 2026-10-12 — Phase 6D: password-protected backups

- From the user's choices (D028): **Create backup** now asks **Protect with a password** (first) or **Plain backup**. Protected backups are one `.csbackup` file encrypted with AES-256-GCM, the key made from your password with scrypt; the password is never saved.
- Protected backups are tagged in the list; **Check** asks for the password and then checks every file; a wrong password or a changed file is reported. **Restore-Studio.cmd** accepts `.csbackup` files and asks for the password. Download gives the protected file as is.
- New `backend/backup_crypto.py`, `tests/test_encrypted_backups.py` (2 tests). Dependency `cryptography` (approved in D022). 6C and 6D are reviewed together.

## 2026-10-12 — Phase 6C-2: region editing and replacing a person

- From the user's choices (D027): replacement uses only that person's approved photos; results from earlier approvals can be edited unless their approval was withdrawn.
- **Edit area** in the result viewer: mark an area (brush, eraser, rectangle, a person's approved box, undo, clear), then **Fix an area** (describe the change) or **Replace a person** (their approved photos). Engines: Codex, OpenAI Images, Gemini image, FLUX.1 Fill (fixes, exact mask) and FLUX 3 (new Black Forest Labs key, Studio settings → Region editing with FLUX).
- Only the marked area is pasted back, with a soft edge inside it; every pixel outside it is exactly the original. Each edit is a new result that links to the result it came from, its marked area and instruction; the viewer compares them.
- API edits ask to confirm the charge; FLUX status checks are free and never resubmit; **Look for a saved image** works for edits. Schema `0012_region_edits`. New `backend/editing.py`, `backend/editing_api.py`, `frontend/src/Edit.tsx`, `tests/test_region_edits.py` (6 tests). No dependencies added; no real provider was called.

## 2026-10-12 — Phase 6C-1: API image engines

- Planned with the user (D025, one question at a time): 6C is built as 6C-1 (API image engines) and 6C-2 (region editing and selective replacement with Codex, OpenAI Images, Gemini image, FLUX.1 Fill for fixes and FLUX 3), with one combined review. Provider facts re-checked (docs/PROVIDER_FINDINGS.md). See D026.
- Studio settings → **Generation engine** now offers **Gemini image** and **OpenAI Images** beside Codex and Manual, grouped like the analysis engines, with the shared API key box, an image model picker (image models listed separately), image size, quality (OpenAI) and the API time limit.
- Generate, Variation, several images per click, Try again and **Generate approved scenes** work with them; every run or batch first shows a charge dialog (what is sent, company, model, size, quality, run count, earlier tokens) and runs only after **…accept charges**. Results show the engine, model, size and reported tokens. Presets can set an image size and quality.
- The provider's image is kept in the run's folder before it is stored; **Look for a saved image** can recover it. Refusals, missing images, unverified OpenAI organisations and limits are reported in plain words; nothing is retried.
- Schema `0011_image_engines`. New `backend/image_api.py`, `tests/test_image_engines.py` (6 tests). The fake provider server understands OpenAI's multipart image edits. No dependencies added; no real provider was called.

## 2026-10-12 — Phase 6A + 6B accepted

- The user's follow-up check passed (`Phase_Checks/Phase6AB_Followup_Report.md`: 14/14 steps, 0 problems, "Phase 6A and 6B look good"), after the combined review (`Phase6AB_Review_Report.md`) whose findings were fixed in D024. The reviews included real Gemini API analyses with the user's free key and a real Claude Code analysis with a chosen model. The Gemini API engine is now `available` in the provider registry; the Anthropic and OpenAI APIs stay `unverified`. Status and handoff updated; `main` pushed to the private GitHub repository with the user's approval (CI not run). 6C and 6D follow in a new chat.

## 2026-10-12 — Phase 6A + 6B review fixes

- From the user's combined review (D024). Studio settings: separate **Analysis engine** and **Generation engine** panels; engines grouped as subscriptions, pay per use and Manual (last), with Subscription / API key tags and live state; only the selected engine's settings (status or API key, model, time limit) show below. The API keys panel is folded into the selected engine.
- Model choice for Claude Code (Default, Opus, Sonnet, Fable) and Codex (Default or a typed name), passed with `--model` / `-m`; used for analysis, Polish prompt and quality checks.
- New searchable model picker with a Recommended tag. A key's model list is fetched when the key is saved and kept; Test key refreshes it.
- Result viewer: "Made from" and "Quality check" stacked full width.
- 10 built-in presets (Individual, Couple, Family, Friends) that can be customised into your own; custom presets get a category and "Save as new preset". The Prompt step's preset controls moved into their own bar with a proper Save as preset button.
- Schema `0010_model_lists` (additive). New `frontend/src/ModelPicker.tsx`, `tests/test_engine_models.py` (2 tests; 129 total).

## 2026-10-12 — Phase 6B: quality checks, presets and comparison

- Started at the user's request; 6A and 6B will be reviewed together with one checklist. See D023.
- **Quality check** in the result viewer: the selected analysis engine compares a result with its Base Image and approved reference photos and scores composition (seven aspects) and each person's identity from 1 to 5, with notes, a summary and things worth fixing. One run per click, cancellable; API engines ask to confirm charges. Result cards show the latest check. Checks are kept per result and can be deleted.
- **Comparison view**: Result, Side by side, Slider, Overlay and Difference, against the Base Image or another result, with shared zoom and pan and optional subject boxes. Select 2–4 results of a scene and choose **Compare** to see them all next to the Base Image.
- **Generation presets** (Studio settings → Generation presets): scene changes, negative additions and images per click. Apply on the Prompt step (rebuilds the draft), choose on the Generate step or in a generation batch; "Save as preset" from the Prompt step. Results record the preset used.
- Schema `0009_quality` (additive). New `backend/quality.py`, `backend/quality_api.py`, `frontend/src/Compare.tsx`, `Quality.tsx`, `Presets.tsx`, `tests/test_quality.py` (6 tests; 127 total). The fake CLI answers checks. No dependencies added.

## 2026-10-11 — Phase 6A: API provider layer and analysis engines

- Approved by the user ("Approve Phase 6"). Phase 6 is delivered in sub-steps 6A–6D; this is 6A. See D022.
- Studio settings: three new analysis engines (**Gemini API**, **Anthropic API**, **OpenAI API**), a model field per engine, an API time limit and a new **API keys** panel (Save, Replace, Remove, Test key). Keys are protected with Windows DPAPI in `<data dir>/keys/`, never shown again, never backed up and kept across a restore.
- Every API run asks first: a dialog shows what is sent, to which company, the model, run count, typical tokens from earlier runs and a prices link. The server refuses API runs, batches, Continue and Try failed again without that confirmation. Runs record the model and the token usage the provider reports.
- API batches pause on a refused key, a missing model or a rate/quota/spending limit. Cancel and time-outs explain that a request already received may still be charged. Nothing is retried.
- Schema `0008_api_engines` (rebuilds two tables to widen CHECK constraints; adds two settings columns). Migrations run with foreign keys off and a full `foreign_key_check` before commit.
- New `backend/keystore.py`, `backend/api_engines.py`, `backend/api_settings.py`, `frontend/src/ApiEngines.tsx`, `tests/test_api_engines.py` (15 tests against a local fake of the three APIs; 121 total). No dependencies added.

## 2026-10-11 — Phase 5.5 accepted

- The user's review passed (`Phase_Checks/Phase5.5_Review_Report.md`: 20/20 steps, 0 problems, "Phase 5.5 looks good", no notes), including real Claude and Codex batches. Phase 5.5 (Batch Processing) is complete. Status and handoff updated; `main` pushed to the private GitHub repository with the user's approval (CI not run). Phase 6 needs "Approve Phase 6".

## 2026-10-11 — Phase 5.5: Batch Processing

- Approved by the user ("Approve Phase 5.5").
- New scene accepts several images; each becomes a scene titled from its file name, and the new scenes stay selected for analysis.
- Scenes Select mode: **Analyse** (one run per scene with the selected engine), **Suggest from group**, **Generate** (approved scenes only) and Delete. **Generate approved scenes** on the toolbar lists every approved scene. Each start dialog shows the run count, which plan allowance it uses, an estimate from earlier runs and what is skipped.
- Batches run one at a time and show progress on the Scenes page, the Overview and the scene itself: Pause, Continue, Cancel remaining, Cancel run, Try failed again, Remove from list. A failed item never stops the batch; usage limit, sign-out or a missing engine pauses it; a restart pauses it with the running item marked Interrupted. Nothing continues or retries on its own.
- Several images from one approval: the Generate step's − / + control (up to 10) queues them as a small batch.
- Group suggestions fill assignments left to right as suggestions that block approval until the user confirms them on the Characters step. Stages "Waiting to analyse" / "Waiting to generate".
- Schema `0007_batches` (additive: `batches`; `engine_jobs.batch_position`). New `backend/batches.py`, `frontend/src/Batches.tsx`, `tests/test_batches.py` (8 tests, 106 total); the fake CLI can hold a run (`FAKE_CLI_GATE`). No dependencies added. See D020.

## 2026-10-11 — Phase 5 accepted

- The user's second follow-up check passed (9/9, 0 problems, "Phase 5 looks good"). Phase 5 (Generation and Results, with the package-copies pop-up and backups/restore) is complete. Status and handoff updated; `main` pushed to the private GitHub repository with the user's approval (CI not run). Phase 5.5 needs "Approve Phase 5.5".

## 2026-10-11 — Phase 5 follow-up fixes (local commit, awaiting second follow-up check)

- From the user's follow-up check (`Phase_Checks/Phase5_Followup_Report.md`: 19/19 steps, 2 flagged, "Needs fixes first"). Approved with "Yes, go ahead".
- Step 3: the average generation time was shown only while Codex was the generation engine; the user's studio was set to Manual. It now always shows when there are finished Codex runs.
- Step 13: backup actions (Download, Check, Delete, Copy path) are compact buttons with line icons instead of text links.
- Step 19: manual package actions (Download, Import result, Copy folder path) use the same buttons, and packages can be deleted (`DELETE /api/exports/{id}`): the folder is removed after a confirmation, imported results are kept with their approval and lose only the package link.
- No schema change, no dependencies added. 98 tests pass (1 new). See D019.

## 2026-10-11 — Phase 5 review fixes (local commit, awaiting follow-up check)

- From the user's Phase 5 review (`Phase_Checks/Phase5_Review_Report.md`: 29/29 steps, 0 problems flagged, "Needs fixes first" because of two notes). The `phase5-additions` branch (package copies, backups) was fast-forwarded into `main` first.
- Generation time: Codex result cards and the viewer show how long the run took; the Generate box shows the average per image over finished Codex runs on this PC; Engine runs show each run's duration. Taken from the job's own start and finish times; imported and recovered results show none.
- Results selection, like Characters, Groups and Scenes: a ⋯ menu on every result card (Download, Mark/Remove preferred, Delete) and a Select mode with a selection bar (Download, Mark as preferred, Remove preferred, Delete) on the Generate step and the Results page. Several results download as one zip (`GET /api/results/download`). The viewer keeps its buttons.
- A scene may now have several preferred results (user's choice), so "preferred" works as a favourite mark.
- Fixed result cards whose text was a few pixels wider than the card. No schema change, no dependencies added. 97 tests pass (existing tests extended). See D018.

## 2026-10-11 — Phase 5 additions: package copies and backups (local branch `phase5-additions`)

- From the user's answers to two open questions. Built in a separate worktree so the Phase 5 review folder stays unchanged.
- Deleting a character or photo whose copies sit in earlier generation or export packages now shows a pop-up with the number of copies, packages and scenes, and asks: Delete and remove copies / Delete, keep copies / Cancel (also for bulk deletion). Nothing is removed without that choice. Removal deletes the numbered copies through the deletion queue, rebuilds export zips, notes it in the README and replaces a deleted character's name in `mapping.txt`; results and approvals are kept. Packages show "N photos removed".
- Backups: Studio settings → Backups (create in the background, check every file, download, delete). Consistent snapshot: database via SQLite's backup API and hard-linked files taken together under the write lock; zip with a SHA-256 manifest. `Restore-Studio.cmd` (studio stopped) verifies the whole backup into a new folder, then swaps it in and keeps the previous data folder renamed; newer-version, damaged or unsafe backups are refused.
- New modules `backend/packages.py`, `backend/backup.py`, `backend/backups_api.py`; `frontend/src/Backups.tsx`; `CopiesDialog` in `Controls.tsx`. No schema change, no dependencies added. 6 new tests (97 total). See D017.

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
