# Session handoff

Checkpoint: 2026-10-10 12:05 IST (+05:30)

## Objective and authorization

The user said **"Approve Phase 3"** on 2026-10-10 (Asia/Kolkata). Phase 3 (Scene Analysis) is implemented and committed locally. The user is now reviewing it with `Phase_Checks/Phase3_Review_Checklist.html` (local only, ignored by Git) and will export `Phase3_Review_Report.md` into the same folder. **Do not push** until the user approves the push after the review. Do not start Phase 4 without "Approve Phase 4".

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). No paid API calls or keys (D009). Every engine run is started by the user; never retried or resumed automatically. Never read or store CLI logins.

## Implemented in this checkpoint (Phase 3)

- Backend modules: `analysis_schema.py` (spike JSON Schema + matching Pydantic models, engine and manual instructions, tolerant parsing of pasted replies), `prompting.py` (studio template), `engines.py` (CLI resolution, clean environment, status, process run with timeout/cancel and tree kill, result interpretation and error kinds), `jobs.py` (queue-ready `JobRunner`, startup reconciliation, job folders), `scene_store.py` (versions, workflow state), `scenes.py` (API). Migration `0004_scenes`. `persistence.writing_session` is shared by the library and scenes. Pending deletions now also remove job folders.
- API: `/api/scenes` (list/create raw-body upload), `/api/scenes/{id}` (get/rename/delete), `/opened`, `/duplicate`, `/image/{original|thumbnail}`, `/analyses` (manual import), `/analyses/{id}/revise`, `/analyse`, `/prompts/draft`, `/prompts`; `/api/jobs/{id}`, `/cancel`; `/api/analysis/instructions`; `/api/engines/settings`, `/api/engines/status`.
- Frontend: `Scenes.tsx` (list, new-scene dialog, workspace with image + subject boxes, analysis view/edit/versions/uncertainties, progress/cancel/error notices, manual dialog, prompt editor and versions, run history), `Engines.tsx` (status and settings), App navigation/Overview (recent scenes, Resume). `api.send` helper with a neutral validation fallback message.
- Workflow states: needs_analysis, analysing, review_analysis, analysis_ready, prompt_saved (derived after each change).
- Decisions: D012.

## Verification evidence

- `uv run --locked pytest`: **69 passed**. `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Fake CLI: `tests/fake_cli.py` (modes: ok, text, signed_out, logged_out_run, limit, invalid, slow; `FAKE_CLI_MODE_FILE` lets browser QA switch modes). Tests assert flags, folder confinement, closed stdin, no leaked variables, provenance, no automatic retry, cancel, restart reconciliation, upgrade 0003→0004.
- Browser QA used the session scratchpad (port 8766) and synthetic images only; QA server stopped afterwards.
- A real CLI analysis has **not** been run by the assistant (plan allowance; user-initiated runs only).

## Runtime and next action

- The user's studio must be restarted to pick up Phase 3. Schema `0004_scenes`.
- Git: local commit for Phase 3 on `main`; not pushed. `origin` is the private `CyberSecurityChuck/Character-Studio`. Push only `main`, never `backup/pre-public-rewrite` or `refs/codex/*`. CI on request only.
- Gotchas carried from the spike: CLIs need clean environments; Codex exit 0 can still mean no image (Phase 5); usage-limit messages were never observed and are matched heuristically.
- Next action: wait for the user's Phase 3 review report. Fix reported problems only with approval. After the user approves, push `main` (and optionally run CI). Phase 4 requires "Approve Phase 4".
