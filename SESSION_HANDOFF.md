# Session handoff

Checkpoint: 2026-10-12 IST (+05:30)

## Objective and authorization

Phase 6 is approved ("Approve Phase 6", 2026-10-11) and delivered as sub-steps 6A–6D (D022). **6A and 6B are complete, accepted and pushed** (2026-10-12; D024 review fixes, follow-up 14/14). On 2026-10-12 the user approved the 6C plan (D025, answered one question at a time): 6C is built as **6C-1** (API image engines) and **6C-2** (region editing and selective replacement), each with its own local commit, then **one combined 6C review**. Choices: Codex is included as the no-charge region editor; FLUX.1 Fill for fixes only (no reference photos); FLUX 3 is also built for replacing a person but the user will not test it now (no costs), so it stays `unverified`; OpenAI Images is built and stays `unverified` until the user verifies the organisation and runs it. The user then said "Record, then build 6C-1". **6C-1 is built and committed locally (D026).** **Do not start 6C-2 without the user's go-ahead.**

Standing rules: no project file changes without the user's approval (describe, then wait for a yes; reading, testing and running the app are fine). Ask decisions one at a time as clickable options with a recommendation and its reason. The assistant never makes paid API calls and never handles real keys. Every engine run is user-started; API runs need the in-studio charge confirmation; nothing is retried or resumed automatically. Never read or store CLI logins. Pushing needs approval each time.

## Implemented in this checkpoint (6C-1, D026)

- Backend: new `backend/image_api.py` (`IMAGE_ENGINES`, `options_for`, `openai_size`, `gemini_ratio`, `send_copies`, `image_request` (Gemini JSON / OpenAI multipart), `read_image_reply`, `openai_error`, `run_image` (writes `output.<ext>` first), `saved_output`, `run_label`). `api_engines.py`: `RawBody` for non-JSON bodies, `list_models` returns (analysis, image) lists. `api_settings.py`: `image_models`, `makes_images`, `suggested_image_model`, `image_charge_note`, `typical_image_usage`; key removal refused for either selected engine. `scenes.py`: `GenerationEngine`, `ImageOptions`, `image_options` in settings (validated per engine), `image_run_settings`, `recoverable` for API runs, `run_label` job names. `results.py`: Generate for any engine with `confirm_charges`; recovery reads `output.*` for API runs. `batches.py`: generation batches for API engines (confirmation, recorded model/size/quality, `_require_generation_engine` on Continue/Retry). `jobs.py`: `_generation_folder`, `_run_api_generation`. `generation.py`: API instruction variant, per-engine timing, `usage` in result data. Presets: `image_size`, `image_quality`. Providers: `gemini_image`, `openai_images` (`unverified`). Migration `0011_image_engines`.
- Frontend: `Engines.tsx` generation panel (groups, key box, image model, size, quality, per-panel save via `applyPanel`); `ApiEngines.tsx` (`imageEngineIds`, `generationNames`, image ChargeSummary); `Scenes.tsx` (charge dialog before API Generate/Try again, confirmed runs and batches); `Results.tsx` (API copy, source labels, usage line); `Mapping.tsx` review cost text; `Batches.tsx` (API generation batches); `Presets.tsx` (size/quality selects); `styles.css` (`.image-options`, `.preset-image-row`); App labels Phase 6C-1, roadmap 6C-2/6D.
- Tests: `tests/test_image_engines.py` (6); fake provider server parses multipart; foundation, migration and settings tests extended.
- Docs: D025 (plan), D026 (6C-1), CHANGELOG, USER_GUIDE (Phase 6C-1 section), RECOVERY, PROVIDER_FINDINGS (6C re-check and implementation notes), README, PROJECT_STATUS, this file.

## Verification evidence

- `uv run --locked pytest`: **135 passed**. `uv run --locked ruff check .`: passed. `npm.cmd --prefix frontend run build`: passed.
- Browser QA on synthetic data (see PROJECT_STATUS): launcher `qa/qa_server.py` and seeding `qa/seed.py` in the session scratchpad (fake CLIs, `FakeProviders` with image replies, `httpx2` client). Screenshots in git-ignored `.playwright-mcp/6c1-*.png`.

## Open questions and notes for the user

- Gemini image uses `generateContent`, which Google now labels "Legacy" (the Interactions API is favoured). It is still documented for image editing; the first real paid run (the user's choice, not planned now) would confirm it.
- D025 said engine and model would join presets; D026 limits presets to image size and quality so a preset can never switch a run to a paid engine. Mention this at review.
- A restart upgrades the user's database through `0011` (0008 and 0011 rebuild tables); back up first.

## Runtime and next action

- The user's studio (http://127.0.0.1:8765) still runs Phase 5.5 code until restarted.
- Git: everything through `b7af410` is pushed to the private `origin/main`. The 6C-1 commit is local only. Every push needs new approval; never push `backup/pre-public-rewrite` or `refs/codex/*`.
- Gotchas: generation engine ids must stay in sync across `IMAGE_ENGINES`, the `0011` CHECK lists, `GenerationEngine`, `imageEngineIds`/`generationNames`; models are stored per purpose (`models[engine]["analysis" | "generation"]`) and each settings panel saves only its own purpose (`applyPanel`); image options are validated against `IMAGE_ENGINES[engine].sizes/qualities`; `scenes.py` imports `backend.quality` (no router) for `preset_image_options`.
- Next action: on the user's go-ahead, **6C-2**: read FLUX 3's API reference first (endpoints, references, box regions, polling), then build region editing (mask drawing, subject-box masks, composite only the masked area back with a feathered edge; pixels outside unchanged and tested), selective replacement (Codex, OpenAI Images, Gemini image, FLUX 3) and FLUX.1 Fill for fixes, each edit a new result version with parent, mask, instruction, engine and model. Then the combined 6C review checklist (`Phase_Checks/Phase6C_Review_Checklist.html`), then 6D (encrypted backups, `cryptography` approved).
