# Session handoff

Checkpoint: 2026-10-12 IST (+05:30)

## Objective and authorization

Phase 6 is approved ("Approve Phase 6", 2026-10-11) and delivered as sub-steps 6A–6D (D022). On 2026-10-12 the user said: "Start 6B for now, I think we'll keep the checklist on hold for now. We can later check 6A and 6B together once done." **6A and 6B are both built and committed locally.** The user's combined review (`Phase_Checks/Phase6AB_Review_Report.md`) asked for fixes; the user approved the fix plan ("Please go ahead") and the fixes are built and committed locally (D024). The follow-up checklist `Phase_Checks/Phase6AB_Followup_Checklist.html` (14 steps; report `Phase6AB_Followup_Report.md`) awaits the user's check. The user said 6C and 6D will be done later in a new chat. Do not start 6C without the user's go-ahead.

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). The assistant never makes paid API calls and never handles real keys. Every engine run is user-started; API runs need the in-studio charge confirmation; nothing is retried or resumed automatically. Never read or store CLI logins. Pushing needs approval each time.

## Implemented in this checkpoint (6B, D023)

- Backend: `backend/quality.py` (check schema and Pydantic models, instruction for CLI files or API images, `prepare_check_folder`, `check_data`/`latest_check`, `preset_name`), `backend/quality_api.py` (`POST /api/results/{id}/check`, `GET /api/results/{id}/checks`, `DELETE /api/checks/{id}`, `GET/POST /api/presets`, `PUT/DELETE /api/presets/{id}`). `jobs.py` `_run_check` (CLI and API). `engines.py`: `analysis_command(instruction, images)`, `structured_reply`. `api_engines.py`: `StructuredTask`, `structured_request` (labelled multi-image), `run_structured`. `workflow.py`: stage `checking`. Results and scenes: `check` and `preset` in result data; result deletion removes checks and is refused during a check; scene deletion removes checks. Generation (single and batch) takes `preset_id` and records the preset name. Migration `0009_quality`. Models `QualityCheck`, `GenerationPreset`.
- Frontend: `Compare.tsx` (Comparison: five modes, shared zoom/pan, boxes), `Quality.tsx` (QualityPanel, Score, checkBadge), `Presets.tsx` (PresetsPanel, PresetDialog, PresetSelect, appendLines). `Results.tsx`: new viewer layout, check chip on cards, Compare in Select mode, preset on the Generate step. `Scenes.tsx`: preset apply / Save as preset on the Prompt step, check progress on the Generate step, stage label. `Batches.tsx`: preset in the generation batch dialog. `ApiEngines.tsx`: ChargeDialog title/action/what. App: presets panel, Phase 6B labels, roadmap 6C/6D. Glyphs `edit`, `compare`.
- Tests: `tests/test_quality.py` (6); `fake_cli.py` answers checks; API analysis test now expects `api-base.jpg` and labelled images.
- Docs: D023, CHANGELOG, USER_GUIDE (Phase 6B section), RECOVERY, README, PROJECT_STATUS, this file.

## Verification evidence

- `uv run --locked pytest`: **127 passed**. `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Browser QA on synthetic data (see PROJECT_STATUS); seeding script `qa/seed6b.py` in the session scratchpad reused `tests.test_mapping.ready_scene` against the live server with `httpx2`. Screenshots in git-ignored `.playwright-mcp/`.

## Open questions and notes for the user

- First real API test is still the user's (free Gemini key, analysis and a check). Checks with Claude/Codex use plan allowance once per click.
- A restart upgrades the user's database through `0008` and `0009`; back up first.

## Runtime and next action

- The user's studio (http://127.0.0.1:8765) still runs Phase 5.5 code until restarted.
- Git: 6A (`88e0690`), 6B (`1f36c1d`), checkpoint (`2c86cd8`) and the review fixes committed locally on `main`; not pushed (needs approval).
- Gotchas: API engine ids must stay in sync across `API_ENGINES`, the `0008` CHECK lists, `EngineSettingsUpdate.AnalysisEngine` and `apiEngineIds`; `api_models` is replaced wholesale on save; check jobs lock the scene like other runs; `quality_api` imports `results`/`scenes`, so `scenes`/`results` must import only `backend.quality` (no router) to avoid cycles.
- Next action (new chat): on "Resume Character Studio", verify these notes against Git (`1f36c1d` 6B, `88e0690` 6A, plus this checkpoint). If the user brings `Phase_Checks/Phase6AB_Followup_Report.md`, fix any findings (with approval); when 6A + 6B are accepted, record the acceptance and push only if approved. Review-fix notes: models are stored per engine in `models` (column `api_models_json`), API model lists in `model_lists_json`, built-in presets in `backend/quality.py` (`BUILTIN_PRESETS`, ids `builtin-…`); the Codex time limit is shared by both settings panels. Then, on the user's go-ahead, 6C: region editing, selective identity replacement and API image engines (OpenAI Images, Gemini image, FLUX Fill; composite only the masked area back onto the original; re-check provider facts first), then 6D: encrypted backups (`cryptography` approved).
