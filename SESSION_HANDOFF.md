# Session handoff

Checkpoint: 2026-10-12 IST (+05:30)

## Objective and authorization

Phase 6 is approved ("Approve Phase 6", 2026-10-11) and delivered as sub-steps 6A–6D (D022). **6A and 6B are complete, accepted and pushed.** On 2026-10-12 the user approved the 6C plan (D025, one question at a time): **6C-1** API image engines and **6C-2** region editing and selective replacement, each with its own local commit, then **one combined 6C review**. The user said "Record, then build 6C-1" and then "Start 6C-2 now". 6C-2 choices (D027): replacing a person sends only that subject's approved photos; results from earlier approvals can be edited unless the user withdrew that approval. **Both 6C-1 (D026) and 6C-2 (D027) are built and committed locally.** The user then said: "We'll now proceed with 6D and then do the review checklist for both of these together, like we did for 6A and 6B." 6D choices (D028): choose each time whether a backup gets a password (password first), and never store the password. **6D is built and committed locally.** The combined review (`Phase_Checks/Phase6CD_Review_Report.md`, "Needs fixes first") is **fixed in D029** (user's choices: keep the withdrawn-approval rule but explain it; success messages as toasts **and** green inline confirmation, everywhere). The follow-up passed (`Phase6CD_Followup_Report.md`: 16/16, 0 problems, "Phase 6C and 6D look good"): **Phase 6 and the whole PLAN.md are complete and accepted (2026-10-12).** The user then asked to update all GitHub-facing docs, make the repository public, push, and run CI (now on every push). All Phase 6 sub-steps are built; do not push or start anything beyond the PLAN.md Phase 6 list without the user's go-ahead.

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). Ask decisions one at a time as clickable options with a recommendation and its reason. The assistant never makes paid API calls and never handles real keys. Every engine run is user-started; API runs need the in-studio charge confirmation; nothing is retried or resumed automatically (FLUX status checks of an already submitted task are free reads, never resubmissions). Never read or store CLI logins. Pushing needs approval each time.

## Implemented in this checkpoint (review fixes, D029)

- Frontend only: new `Toast.tsx` (`notify`, `Toaster` in the App shell, `StatusNote`, `toneOf`); `StatusNote` replaces the `library-status` lines in ApiEngines, Backups, Library, Presets, Results, Scenes; green `saved-flag` in the Engines footers and the studio-name form; toasts for engine saves, studio name and successful backup checks; visible Edit area note in the result viewer; GeneratePanel package-deletion errors in their own alert. Styles at the end of `styles.css`.
- The user's own data: results 1 and 3 belong to approval `e4e13290…`, withdrawn 2026-10-11; the scene's current approval has no results. Nothing in the user's data was changed (read-only checks).

## Earlier in this session (6D, D028)

- Backend: new `backend/backup_crypto.py` (`encrypt_file`, `decrypt_file`, `read_header`, `is_encrypted`, `check_password`; AES-256-GCM chunks, scrypt). `backup.py`: `create_backup(password)` seals the zip into `.csbackup`, `NAME` accepts both extensions, `backup_info` (encrypted: date from the name, no counts), `open_backup`, `verify_backup(password)`, `BackupRunner.start(password)`, restore console asks with `getpass`. `backups_api.py`: `CreateInput`/`PasswordInput` (password checked in code only), download content type. `Restore-Studio.cmd` comment. Dependency `cryptography` (pyproject + uv.lock).
- Frontend: `Backups.tsx` CreateDialog (kind cards, password twice, show toggle, rules, warning, hidden username) and PasswordDialog for Check; lock tag; counts after a check. Glyph `lock`. App: roadmap empty (section hidden), label "Encrypted backups · Phase 6D".
- Tests: `tests/test_encrypted_backups.py` (2). Docs: D028, CHANGELOG, USER_GUIDE, RECOVERY, README, PROJECT_STATUS, this file.

## Earlier in this session (6C-2, D027)

- Backend: new `backend/editing.py` (`EDIT_OPTIONS`, `read_mask`, `mask_box`, `composite` (feather × mask, outside pixels untouched), `usable_approval` (withdrawn → refused), `replaceable`, `prepare_edit_folder`, `edit_instruction`, `flux3_prompt`, OpenAI/Gemini/FLUX request builders, `run_api_edit`, `run_flux` (submit + polling, `submitted.json`), `flux_poll_once`, `_trusted` hosts, `finish_edit`, `edit_label`), new `backend/editing_api.py` (`GET /api/edit-options`, `POST /api/results/{id}/edit`, `GET /api/results/{id}/mask`, `store_edit`, `recover_edit`). `jobs.py`: `_run_edit`, `_codex_edit`. `api_engines.py`: `bfl_api` engine (`analysis=False`, `x-key`, credits check, 402 → usage limit), `BFL_MODELS`. `generation.py`: `store_result(parent_result_id, edit)`, `approval_boxes`, result data `parent_result_id`, `edit`, `mask_url`, `editable`, mapping `box`. `results.py`: recovery for edits, deletion blocked during edits. `scenes.py`: `recoverable()`, edit job names. Workflow stage `editing`. `configuration.ASSET_DIRECTORIES` + `masks`. Providers `flux_fill`, `flux_3` (`unverified`). Migration `0012_region_edits`.
- Frontend: new `Edit.tsx` (EditDialog: canvas mask, tools, person areas, kind, subject, instruction, engine cards with availability, Codex confirm / ChargeDialog). `Results.tsx`: Edit area button, edit note, compare with parent, source labels "Edited · …"/"Replaced Subject N · …", credits in usage line. `ApiEngines.tsx`: `costLine`. `Engines.tsx`: FLUX key box and privacy text. `Scenes.tsx`: edit progress, notices (no Try again for edits), stage label, run history label. `Controls.tsx` glyphs brush/eraser/rect/undo. Styles for the edit dialog. App label "Region editing · Phase 6C".
- Tests: `tests/test_region_edits.py` (6); the fake provider server now imitates FLUX (submit, polling statuses, sample download, credits).
- Docs: D027, CHANGELOG, USER_GUIDE (Phase 6C-2 section), RECOVERY, PROVIDER_FINDINGS (FLUX 3 facts and implementation notes), README, PROJECT_STATUS, this file.

## Verification evidence

- `uv run --locked pytest`: **143 passed** (after 6D; 141 after 6C-2). `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Browser QA on synthetic data (see PROJECT_STATUS): launcher `qa/qa_server.py`, seeds `qa/seed.py` and `qa/seed_edit.py` in the session scratchpad. Screenshots in git-ignored `.playwright-mcp/6c1-*.png` and `6c2-*.png`.

## Open questions and notes for the user

- Gemini image uses `generateContent` ("Legacy" on Google's site, still documented); FLUX 3's box-row format is inferred from BFL's guide pages. Both are confirmed only by a real paid run, which the user does not plan now.
- D026: presets carry image size and quality only (not engine or model), so a preset never switches to a paid engine.
- Codex and Gemini cannot use a mask; their whole image is generated and only the marked area is kept. If they shift the framing, the pasted area can look misaligned; FLUX.1 Fill follows the mask exactly.
- A restart upgrades the user's database through `0012` (0008, 0011, 0012 rebuild tables); back up first.

## Runtime and next action

- The user's studio (http://127.0.0.1:8765) still runs Phase 5.5 code until restarted.
- Git: everything through `b7af410` is pushed to the private `origin/main`. 6C-1 (`0de46f7`), 6C-2 (`d695092`) and 6D are local only. Every push needs new approval; never push `backup/pre-public-rewrite` or `refs/codex/*`.
- Gotchas: generation engine ids stay in sync across `IMAGE_ENGINES`, the CHECK lists (0011/0012), `GenerationEngine`, `imageEngineIds`/`generationNames`; `bfl_api` is in `API_ENGINES` but `analysis=False` and not in `apiEngineIds`; `jobs.py` imports `editing_api.store_edit` lazily and `results.recover_images` imports `recover_edit` lazily (import cycles through `scenes`); edit masks are stored at the result's upright size.
- Next action: follow PROJECT_STATUS "Making the GitHub repository public": visibility change (confirmed with the user), push `main` only, check CI, then (with the user's OK) enable secret scanning, push protection and private vulnerability reporting. The user kept both success styles (toast + green inline) for now. Nothing beyond PLAN.md Phase 6 is approved.
