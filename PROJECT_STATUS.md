# Project status

Last checkpoint: 2026-10-12 IST (+05:30)

- Phase: 6 (Quality and advanced features) **approved** ("Approve Phase 6", 2026-10-11) and delivered in sub-steps (D022): **6A API provider layer and analysis engines (built)**, **6B quality checks, presets and comparison (built)**, 6C region editing, selective identity replacement and API image engines (OpenAI Images, Gemini image, FLUX Fill), 6D encrypted backups (`cryptography` approved). By the user's choice (2026-10-12), **6A and 6B are reviewed together**: the combined checklist `Phase_Checks/Phase6AB_Review_Checklist.html` (30 steps, report `Phase6AB_Review_Report.md`) is written and **awaiting the user's review**; the 6A-only checklist was deleted. **6C and 6D are planned for a new chat.** Phases 1–5.5 are complete and accepted.
- Approval: "Approve Phase 2" (2026-10-09), "Approve Phase 2.5" and "Approve Phase 3" (2026-10-10), "Approve Phase 4", "Approve Phase 5", "Approve Phase 5.5" and "Approve Phase 6" (2026-10-11, Asia/Kolkata). The full starting set of API engines is approved for building (off by default). The assistant makes no paid calls and handles no real keys. Pushing needs new approval for every push. CI only on request. Standing rule: no project file changes without the user's approval.
- Completed 6A (D022): Gemini/Anthropic/OpenAI API analysis engines; DPAPI-protected keys outside backups; server-enforced charge confirmation; model and token usage per run; schema `0008_api_engines`.
- Completed 6B (D023): **quality checks** (job kind `check`, selected analysis engine, Base Image + approved references + result; composition aspects and per-person identity scored 1–5 with notes; stored in `quality_checks`; lowest scores shown; stage "Checking a result…"); **comparison view** (Result, Side by side, Slider, Overlay, Difference; against the Base Image or another result; shared zoom/pan; subject boxes; Compare 2–4 selected results); **generation presets** (`generation_presets`: scene changes, negative additions, images per click; applied on the Prompt step, Generate step and generation batches; preset name recorded on runs). Schema `0009_quality` (additive).
- Verification: `uv run --locked pytest` — **127 passed** (6 new in `tests/test_quality.py`: Claude and Codex checks, engine/format errors, API check with confirmation and multi-image request, deletion rules, presets and their recording). `uv run --locked ruff check .` — passed. `npm.cmd --prefix frontend run build` — passed. Browser QA (Playwright, synthetic scratchpad data, port 8766, fake CLIs and fake API server): viewer modes, 2× zoom with boxes, Check quality with Claude (confirm → result panel), Compare 2 results, Difference mode, preset applied on the Prompt step (draft rebuilt, negatives added once), preset dialog, Generate step preset, 1440 and 375 px; no console errors besides the favicon 404. Fixed during QA: second orange primary button in the viewer, box outline blur when zoomed, preset row pushing Variation onto a new line, reversed picker labels in multi-compare.
- Real engines: not run by the assistant. API engines stay `unverified` until the user's first real run.
- Runtime: the user's studio at http://127.0.0.1:8765 still runs Phase 5.5 code until restarted; a restart upgrades the database to `0009_quality` (0008 rebuilds two tables; 0009 is additive). Back up first. Data: `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid calls by the assistant. No dependencies added in 6A or 6B.
- Git: 6A committed locally (`88e0690`); 6B committed locally on top. Not pushed. Remote `origin` = `CyberSecurityChuck/Character-Studio` (**private**).

Earlier history (Phase 2 review, plan v2.1, Phase 2.5 spike, public-release prep, Phases 3–5.5) is in CHANGELOG.md and DECISIONS.md D008–D021; Phase 6 is D022 (6A) and D023 (6B).

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.**
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
