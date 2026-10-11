# Project status

Last checkpoint: 2026-10-11 IST (+05:30)

- Phase: 6 (Quality and advanced features) **approved** ("Approve Phase 6", 2026-10-11). Per the user's answers it is delivered in sub-steps, each with a local commit and a Phase_Checks review: **6A API provider layer and analysis engines (built, awaiting the user's review)**; 6B identity/composition checks, saved presets, comparison view; 6C region editing, selective identity replacement, API image engines (OpenAI Images, Gemini image, FLUX Fill); 6D encrypted backups (`cryptography` dependency approved). Phases 1–5.5 are complete and accepted. See DECISIONS.md D022.
- Approval: "Approve Phase 2" (2026-10-09), "Approve Phase 2.5" and "Approve Phase 3" (2026-10-10), "Approve Phase 4", "Approve Phase 5", "Approve Phase 5.5" and "Approve Phase 6" (2026-10-11, Asia/Kolkata). The full starting set of API engines is approved for building (off by default). The assistant makes no paid calls and handles no real keys. Every paid run is confirmed by the user in the studio. Pushing needs new approval for every push. CI runs only on request. Standing rule: no project file changes without the user's approval.
- Completed (6A, D022): analysis engines **Gemini API**, **Anthropic API** and **OpenAI API** beside Claude, Codex and Manual. Keys in Studio settings → API keys (Save, Replace, Remove, Test key). They are DPAPI-protected in `<data dir>/keys/`, write-only from the browser, not in backups and moved across on restore. There is a model field per engine and an API time limit. The server enforces charge confirmation (`confirm_charges`) for single analyses, analysis batches, Continue and Try failed again. The dialog shows what is sent, to whom, the model, the run count, typical tokens and a prices link. Jobs record the model and token usage. API batches pause on key_problem, model_problem and usage_limit. Cancel and timeout say a received request may still be charged. Nothing is retried.
- Persistence: schema `0008_api_engines` (rebuilds `engine_settings` and `scene_analyses` to widen CHECK constraints; adds `api_timeout`, `api_models_json`). Migrations now run with foreign keys off plus `PRAGMA foreign_key_check` before commit.
- Verification: `uv run --locked pytest` — **121 passed** (15 new in `tests/test_api_engines.py` against a local fake of the three APIs; the upgrade test now also recreates the Phase 3 settings table and checks the new CHECK constraints). `uv run --locked ruff check .` — passed. `npm.cmd --prefix frontend run build` — passed. Browser QA (Playwright, isolated synthetic scratchpad data, port 8766, fake CLIs and fake API server): saved a synthetic key, Test key, chose `gemini-2.5-flash`, selected Gemini, Analyse → charge dialog → run → version labelled Gemini API with model, time and tokens; analysis batch of 2 with the charge summary; Remove disabled for the selected engine; 1440 and 375 px; no console errors besides the existing favicon 404. Fixed during QA: batch summary said "using your own sign-in" for API engines. QA server stopped.
- Real APIs: **not called**. The engines are `unverified` in the provider registry until the user's first real run (Gemini free key, analysis only).
- Runtime: the user's studio at http://127.0.0.1:8765 still runs Phase 5.5 code until it is restarted. On restart it upgrades the database to `0008_api_engines`; creating a backup first is advisable. Data: `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid calls by the assistant. No dependencies added in 6A.
- Git: 6A committed locally (not pushed). Remote `origin` = `CyberSecurityChuck/Character-Studio` (**private**). Push only `main`, only with approval. CI on request (`gh workflow run CI`).

Earlier history (Phase 2 review, plan v2.1, Phase 2.5 spike, public-release prep, Phases 3–5.5) is in CHANGELOG.md and DECISIONS.md D008–D021; Phase 6 is D022.

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.**
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
