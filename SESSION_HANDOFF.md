# Session handoff

Checkpoint: 2026-10-11 IST (+05:30)

## Objective and authorization

The user said **"Approve Phase 4"** on 2026-10-11 (Asia/Kolkata). Phase 4 (Character Mapping and Approval) is **complete and accepted** ("Phase 4 accepted", 2026-10-11) after the review (`Phase_Checks/Phase4_Review_Report.md`), the review fixes (D015) and the follow-up check (`Phase_Checks/Phase4_Followup_Report.md`). The user approved pushing `main` once for the Phase 4 commits; every later push needs new approval. Do not start Phase 5 without "Approve Phase 5".

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). No paid API calls or keys (D009). Every engine run is started by the user; never retried or resumed automatically. Never read or store CLI logins.

## Implemented in this checkpoint (Phase 4)

- Backend: new `workflow.py` (subjects fingerprint, automatic reference selection, `build_plan`, `save_mappings`, approval snapshots, `check_approval` / `revalidate_approval` / `require_valid_approval`, `review` blockers/warnings/notes, `refresh_workflow` and `add_analysis` moved here from `scene_store.py`, which keeps only small queries). `prompting.py`: `Assignment`, identity-assignment lines, `check_prompt`, polish rules and `polish_instruction`. `engines.py`: `polish_command`, `interpret_polish`, shared Claude envelope reading. `jobs.py`: polish runs (`jobs/<scene>/polish-<n>/`). `library.py`: photo content hashes (upload + startup backfill), `assigned_scene_count`, deletion effects on mappings/approvals, group deletion clears `scenes.mapping_group_id`. Migration `0005_mapping`.
- API: `PUT /api/scenes/{id}/mappings`, `PUT /api/scenes/{id}/subjects`, `POST /prompts/check`, `POST /polish`, `POST /prompts/polished`, `POST /prompts/polished/{job}/keep-original`, `POST /approve`, `POST /approval/withdraw`. Scene detail adds `subjects`, `mapping_group_id`, `mapping_hash`, `total_images`, `review`, `approval`, `approvals`, `pending_polish`; prompts carry `mapping_hash`, `is_polished`, `polished_from_version_id`.
- Workflow states: needs_analysis, analysing, polishing, review_analysis, needs_mapping, analysis_ready ("Ready for prompt"), prompt_saved ("Ready to approve"), approved.
- Frontend: `Mapping.tsx` (SubjectCanvas, MappingPanel, ReferencePicker, PolishDialog with word diff, ReviewPanel). `Scenes.tsx` step tabs and wiring; `Library.tsx` exports Avatar/types and scene-aware delete messages; App/Engines copy for Phase 4.
- Decisions: D014.

## Verification evidence

- `uv run --locked pytest`: **81 passed**. `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Fake CLI (`tests/fake_cli.py`) now also answers polish runs (modes `ok`, `drop` = loses Subject 1's lines, plus the existing failure modes).
- Browser QA used the session scratchpad (port 8766), drawn fictional characters and a drawn scene only; QA server stopped afterwards.
- A real CLI polish has **not** been run by the assistant (plan allowance; user-initiated runs only).

## Phase 4 review fixes (D015)

- The user's review (`Phase_Checks/Phase4_Review_Report.md`, 34/34, "Needs fixes first") reported a clipped box label, no visible resizing, no warning after deleting the identity instruction in a polish edit, and asked for deleting prompt versions. Approved: "Yes, please go ahead with all four fixes".
- Done and committed locally: removed the leftover `.subject-box span` CSS rule; eight handles on the selected box (`SubjectCanvas`, `HANDLES`); `check_prompt` "identity comes only from" requirement; `DELETE /api/scenes/{id}/prompts/{prompt_id}`, `workflow.next_prompt_version`, `approval_data.prompt_id`, `PromptHistory` dialog replacing the versions dropdown. 82 tests pass.
- Follow-up checklist: `Phase_Checks/Phase4_Followup_Checklist.html`; report `Phase4_Followup_Report.md` (13/13, "Needs fixes first": step 5, the comparison marked nothing on a long real prompt because the word diff gave up above ~3M cells). Fixed in `Mapping.tsx` `diffWords`/`compare` (lines first, then words in changed passages, 12M-cell limit, removed/added counts). The user accepted Phase 4 after this fix.

## Runtime and next action

- The user's studio runs Phase 4 (schema `0005_mapping`).
- Git: Phase 4 commits on `main`, pushed to `origin` with the user's approval (2026-10-11). `origin` is the private `CyberSecurityChuck/Character-Studio`. Push only `main`, never `backup/pre-public-rewrite` or `refs/codex/*`. CI on request only.
- Gotchas: a fresh analysis deliberately marks assignments for re-checking; the polish instruction is one CLI argument (limit ~24,000 characters); provider reference-image limits are unverified (note above 4 photos).
- Next action: wait for "Approve Phase 5". At the end of each phase: update docs, commit locally, create `Phase_Checks/PhaseN_Review_Checklist.html`, and push only after the user's review approval. Phase 5 (Generation and Results) needs "Approve Phase 5" and must gate every run with `workflow.require_valid_approval`.
