# Project status

Last checkpoint: 2026-10-11 IST (+05:30)

- Phase: 5.5 — Batch Processing **built, committed locally, awaiting the user's review** (`Phase_Checks/Phase5.5_Review_Checklist.html`). Approved with "Approve Phase 5.5" (2026-10-11). Phase 5 (Generation and Results) is complete and accepted (2026-10-11). Next phase: 6 (Quality and advanced features), not started; needs explicit approval.
- Approval: "Approve Phase 2" (2026-10-09), "Approve Phase 2.5" and "Approve Phase 3" (2026-10-10), "Approve Phase 4", "Approve Phase 5" and "Approve Phase 5.5" (2026-10-11, Asia/Kolkata). Phase 6 and later and paid API calls are **not** authorized. Pushing needs new approval for every push (the last approved push was the Phase 5 acceptance, 2026-10-11). CI runs only on request. Standing rule: no project file changes without the user's approval.
- Completed (Phase 5.5, D020): New scene accepts several images (one scene each, up to 30, uploaded one by one through the existing endpoint; the new scenes stay selected). Scenes Select mode adds **Analyse**, **Suggest from group** and **Generate**; the toolbar adds **Generate approved scenes**. Start dialogs show run count, plan allowance, estimate and skipped scenes. Batches (`batches` table + ordinary `engine_jobs` with `batch_id`/`batch_position`) run one at a time, single clicks first; Pause (run in progress finishes), Continue (checks sign-in first), Cancel remaining, Cancel run, Try failed again (new items with `retry_of`), Remove from list. Failed items never stop a batch; usage limit / signed out / not installed pause it (and other running batches on that engine); a pre-run sign-in problem returns the item to not_started. Restart: running item Interrupted, batch paused, waiting items kept. Several images from one approval via the Generate step's − / + (up to 10). Group suggestions (left to right, stored as `subjects_hash = "suggested"`) block approval until confirmed. Stages "Waiting to analyse" / "Waiting to generate"; waiting scenes offer **Remove from batch**. Batch panels on the Scenes page, Overview and inside the scene.
- Limits: 50 analyses or 20 images per batch; 1–5 images per scene in a batch.
- Persistence: schema `0007_batches` (additive: `batches`; `engine_jobs.batch_position` + index on `batch_id`).
- Verification: `uv run --locked pytest` — **106 passed** (8 new in `tests/test_batches.py`; the Phase 4→5 upgrade test now also undoes 0007). Batch tests repeated 3× without failures. `uv run --locked ruff check .` — passed. `npm.cmd --prefix frontend run build` — passed. Browser QA (Playwright, isolated synthetic data folder in the session scratchpad, port 8766, fake CLIs with a hold gate, drawn fictional characters "Mira" and "Teo"): 4 images → 4 scenes selected; Analyse 4 with Pause → paused after the running item → waiting card in a scene → Continue; Suggest from group → notice → Confirm assignments; Generate approved scenes (2 per scene) with a simulated plan limit → paused with reason → Continue → Try failed again; 3 variations from one scene with the progress card and compact batch card; 1440 px and 375 px; no console errors besides the existing favicon 404. Fixed during QA: stage chip stayed "Waiting" after the item started; batch card dominated the scene view; retry wording; empty-selection hint. QA server stopped; no stray processes.
- Not verified: real CLIs. The assistant ran no real Claude or Codex runs (plan allowance; user-initiated runs only). Usage-limit wording for real Codex/Claude is still matched heuristically (PROVIDER_FINDINGS).
- Runtime: the user's studio at http://127.0.0.1:8765 needs a restart to load Phase 5.5 (migration `0007_batches` runs on start). Data: `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid API clients or keys. Batches only use plan allowances when the user starts or continues them. No dependencies added.
- Git: Phase 5.5 committed locally on `main`, **not pushed**. Remote `origin` = `CyberSecurityChuck/Character-Studio` (**private**). Push only `main`, and only with approval. CI on request (`gh workflow run CI`).

Earlier history (Phase 2 review, plan v2.1, Phase 2.5 spike, public-release prep, Phases 3–5) is in CHANGELOG.md and DECISIONS.md D008–D019; Phase 5.5 is D020.

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.** (Without these, website edits sign commits with the personal Gmail, as happened earlier that day.)
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
