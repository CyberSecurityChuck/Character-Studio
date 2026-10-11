# Session handoff

Checkpoint: 2026-10-11 IST (+05:30)

## Objective and authorization

The user said **"Approve Phase 5.5"** on 2026-10-11 (Asia/Kolkata). Phase 5.5 (Batch Processing) is built and committed locally; it awaits the user's review with `Phase_Checks/Phase5.5_Review_Checklist.html` (git-ignored). Phase 5 is complete and accepted. Do not start Phase 6 without explicit approval. Pushing needs the user's approval each time.

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). No paid API calls or keys (D009). Every engine run is started by the user; batches run only after the user starts or continues them; nothing is retried or resumed automatically. Never read or store CLI logins.

## Implemented in this checkpoint (Phase 5.5, D020)

- Backend: migration `0007_batches` (table `batches`; `engine_jobs.batch_position`; index on `batch_id`); model `Batch`. New `backend/batches.py`: `GET /api/batches`, `GET /api/batches/timing`, `GET /api/batches/{id}`, `POST /api/batches/analysis`, `POST /api/batches/generation`, `POST /api/batches/{id}/pause|continue|cancel|retry`, `DELETE /api/batches/{id}`, `POST /api/scenes/suggest-group`. `jobs.py`: claims batch items only while their batch is running, single runs first; `PAUSE_KINDS` (usage_limit, signed_out, not_installed) pause batches via `pause_batches`; pre-run sign-in failures in a batch return the item to not_started (`_NotSent`); startup keeps waiting batch items and pauses their batches ("restart"); the scene stage is refreshed when an item is claimed. `workflow.py`: stages `waiting_analysis` / `waiting_generation`; `SUGGESTED` mappings and their blocker. `scene_store.active_job` prefers the running job. `scenes.py`: job data adds `batch_id` and `batch` (position, total, status); subjects add `suggested`. Bootstrap phase 5.5.
- Frontend: new `Batches.tsx` (`BatchList`, `BatchCard`, `BatchDialog`, `GroupDialog`). `Scenes.tsx`: multi-image New scene form, selection actions, Generate approved scenes, batch panel, batch-aware progress card ("Remove from batch"), stage update when an item starts, generate with a count. `Results.tsx`: − / + images control. `Mapping.tsx`: suggestion notice and Confirm assignments. `App.tsx`: Overview "Batches in progress", Phase 5.5 labels, roadmap. Styles for batches.
- Tests: `tests/test_batches.py` (8); `fake_cli.py` waits for `FAKE_CLI_GATE` when set; the upgrade test in `test_generation.py` also undoes 0007.
- Docs: README, USER_GUIDE (Batches section), RECOVERY (Phase 5.5 section), DECISIONS D020, CHANGELOG, AGENTS.md approval line, PROJECT_STATUS.

## Verification evidence

- `uv run --locked pytest`: **106 passed**; batch tests repeated 3× clean. `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Browser QA with Playwright on an isolated synthetic data folder (session scratchpad, port 8766, fake CLIs, drawn fictional characters): multi-upload, Analyse selected with Pause/Continue, waiting and paused cards, Suggest from group and Confirm, Generate approved scenes with a simulated plan limit, Continue, Try failed again, 3 variations from one scene, 1440 and 375 px, no console errors (only the existing favicon 404). The in-app browser pane could not take screenshots (window in the background), so Playwright was used.
- Real CLIs were not run by the assistant.

## Scope notes and open questions for the user

- Extension beyond the plan's wording, recorded in D020: "not installed" also pauses a batch; single clicks run before waiting batch items; Try failed again is offered only once a batch has finished.
- Known headless-only artefact: at 375 px in desktop Chromium with classic scrollbars every page is 18 px wider than the viewport because of the existing sidebar row; not caused by Phase 5.5 and not seen with overlay scrollbars.

## Runtime and next action

- The user's studio (http://127.0.0.1:8765) must be restarted to load Phase 5.5 (schema `0007_batches`).
- Git: Phase 5.5 committed locally on `main`, **not pushed**. Push only `main` and only with approval; never `backup/pre-public-rewrite` or `refs/codex/*`. CI on request only.
- Gotchas: waiting batch items count as active runs (scenes locked until removed from the batch or run); Cancel remaining never stops a running item; `/api/batches/timing` must stay declared before `/api/batches/{batch_id}`.
- Next action: wait for the user's Phase 5.5 review report; apply approved fixes; record acceptance; ask before pushing.
