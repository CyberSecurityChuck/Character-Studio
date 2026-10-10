# Project status

Last checkpoint: 2026-10-10 12:05 IST (+05:30)

- Phase: 3 — Scene Analysis **implemented and committed locally; awaiting the user's hands-on review** (`Phase_Checks/Phase3_Review_Checklist.html`). Phase 3 remains the active phase until the user approves it.
- Approval: "Approve Phase 2" (2026-10-09), "Approve Phase 2.5" and "Approve Phase 3" (2026-10-10, Asia/Kolkata). Phase 4 and later, paid API calls and pushing to GitHub are **not** authorized. The user will approve the push after finishing the Phase 3 checks. Standing rule: no project file changes without the user's approval.
- Completed (Phase 3): scenes (Base Image upload with validation, thumbnail, dimensions, content hash; rename, duplicate, delete, resume, recent scenes on the Overview); versioned scene analysis validated by one schema for the Claude CLI engine, the Codex CLI engine and the manual import; uncertain details flagged for Confirm/Correct; analysis editing as new versions; studio prompt template (numbered images, "Subject N", identity and composition locks, negative prompt, scene changes) with saved, restorable prompt versions; queue-ready engine job runner (one job at a time, Not started/Running/Completed/Failed/Cancelled/Interrupted, optional batch id) with timeout and Cancel; engine settings (analysis engine Claude/Codex/Manual, generation engine Codex/Manual for Phase 5, per-engine time limits) and engine status with "Check again".
- Engines: only Phase 2.5-confirmed flags. Each run gets `jobs/<scene>/analysis-<n>/` in the private data folder with a metadata-free `base.jpg`; stdin closed; `CLAUDE*`, `ANTHROPIC*`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `CODEX_API_KEY` removed from the environment; sign-in checked first; never retried. On Windows the npm `codex.cmd` shim is bypassed by running its own `codex.js` with node (D012).
- Persistence: schema `0004_scenes` (additive; adds `engine_settings`, `scenes`, `scene_analyses`, `prompt_versions`, `engine_jobs`). At startup, running jobs become Interrupted and waiting jobs Cancelled; nothing resumes.
- Verification: `uv run --locked pytest` — **69 passed** (20 new, using a fake CLI that mirrors the spike's argument and output shapes); `uv run --locked ruff check .` — passed; TypeScript/Vite build — passed. Browser QA on an isolated synthetic data folder (port 8766) with the fake CLI: create, analyse, cancel (no stray processes), retry, confirm uncertainty, edit analysis, manual import error, prompt rebuild/save, settings, overview, usage-limit error, hard-kill interruption, duplicate, 375 px width, no console errors.
- **Not yet verified:** a real `claude`/`codex` analysis through the studio. The first real Analyse should be the user's own click during review (it uses plan allowance).
- Runtime: normal studio at http://127.0.0.1:8765 must be **restarted** (Stop-Studio.cmd, Start-Studio.cmd) to load Phase 3; the startup migration to `0004_scenes` is additive. Data: `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid API clients or keys. CLI runs use the user's plan allowance only when the user clicks. No dependencies added.
- Pending: user review of Phase 3; then push `main` to GitHub after explicit approval; Phase 4 needs "Approve Phase 4".
- Git: see `git log -5 --oneline` / `git status --short`. Remote `origin` = `CyberSecurityChuck/Character-Studio` (**private**). Push only `main`, and only with approval. CI runs on request (`gh workflow run CI`).

Earlier history (Phase 2 review, plan v2.1, Phase 2.5 spike, public-release prep) is in CHANGELOG.md and DECISIONS.md D008–D011.

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.** (Without these, website edits sign commits with the personal Gmail, as happened earlier that day.)
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
