# Project status

Last checkpoint: 2026-10-11 IST (+05:30)

- Phase: 4 — Character Mapping and Approval **built and reviewed; review fixes committed locally, awaiting the user's follow-up check** (`Phase_Checks/Phase4_Followup_Checklist.html`). Review: `Phase_Checks/Phase4_Review_Report.md` (34/34, 0 flagged, "Needs fixes first"). Fixes (D015): box labels, eight-handle resizing, identity-only check, prompt Version history with delete. Phase 3 was accepted on 2026-10-11.
- Approval: "Approve Phase 2" (2026-10-09), "Approve Phase 2.5" and "Approve Phase 3" (2026-10-10), "Approve Phase 4" (2026-10-11, Asia/Kolkata). Phase 5 and later and paid API calls are **not** authorized. Pushing needs new approval for these commits (the one-time push approval covered the Phase 3 commits only). CI runs only on request. Standing rule: no project file changes without the user's approval.
- Completed (Phase 4): four-step scene workspace (Analysis, Characters, Prompt, Review; step kept in the address). Subject assignment per subject (Use a character / Keep original / Decide later), one character per subject, group filter that never assigns anyone, automatic or manual reference photo selection with image numbers, subject box move/resize/add/remove as analysis versions (labels never renumber), re-check after a fresh analysis. Prompt template with identity assignments and keep-original lines (no character names), required-element check. Optional Polish prompt (Claude, text only) with comparison, word-level highlights, Use polished / Keep original / Edit by hand and explicit acceptance of missing elements. Review screen and immutable approval snapshots with content hashes, file verification, automatic cancellation with reasons (including library deletions and offline changes found at startup), withdraw, history. `workflow.require_valid_approval` is the Phase 5 gate.
- Persistence: schema `0005_mapping` (additive: `subject_mappings`, `approvals`; columns `reference_photos.content_hash`, `scenes.mapping_group_id`, `prompt_versions.mapping_hash`, `engine_jobs.input_id/output_text/decision`). Photo hashes are backfilled at startup. Approvals are re-checked at startup and after every change.
- Verification: `uv run --locked pytest` — **81 passed** (12 new in `tests/test_mapping.py`; two Phase 3 expectations changed from "Ready for prompt" to the new "Assign characters" stage; shared engine fixtures moved to `tests/conftest.py`). `uv run --locked ruff check .` — passed. `npm.cmd --prefix frontend run build` — passed. Browser QA on an isolated synthetic data folder (port 8766, fake CLI, drawn fictional characters): analyse, confirm, assign, automatic photos and image numbers, keep original, prompt draft, polish + compare + missing-element warning on a hand edit, use polished, approve, photo deletion cancelling approval with a reason and flagging "Image 4", subject box drag/add/save, 1440 px and 375 px widths, no console errors. QA server stopped; no stray processes.
- Runtime: the user's studio at http://127.0.0.1:8765 must be restarted to run Phase 4 (migration `0005_mapping` runs on start). Data: `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid API clients or keys. Polish uses the user's Claude plan allowance only when clicked. Nothing is sent to OpenAI in Phase 4. No dependencies added.
- Review fixes (2026-10-11): leftover Phase 3 `.subject-box span` rule removed (it hid label text and the resize handle); eight resize handles on the selected box; `check_prompt` requires "identity comes only from Image …" per replaced subject; `DELETE /api/scenes/{id}/prompts/{prompt_id}` (refused for the approved or polishing version; approved version numbers never reused) and a Version history dialog. `uv run --locked pytest` — **82 passed**; Ruff and build passed; browser QA (labels, side and corner resizing, history list/preview/delete, 375 px, no console errors).
- Not yet done by the assistant: a real `claude` polish run (`--tools ""` is from `--help`, not yet exercised for real); the user's review includes one.
- Git: see `git log -5 --oneline` / `git status --short`. Remote `origin` = `CyberSecurityChuck/Character-Studio` (**private**). Push only `main`, and only with approval. CI on request (`gh workflow run CI`).

Earlier history (Phase 2 review, plan v2.1, Phase 2.5 spike, public-release prep, Phase 3) is in CHANGELOG.md and DECISIONS.md D008–D014.

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.** (Without these, website edits sign commits with the personal Gmail, as happened earlier that day.)
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
