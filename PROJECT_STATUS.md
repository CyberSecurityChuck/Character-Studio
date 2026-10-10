# Project status

Last checkpoint: 2026-10-10 04:10 IST (+05:30)

- Phase: 2 — Character Library implemented, reviewed hands-on by the user, and refined from that review. Phase 2 remains the active phase.
- Approval: Explicit "Approve Phase 2" on 2026-10-09 (Asia/Kolkata). Phases 1–2 and local checkpoints authorized. Phase 3 and later, paid AI calls and remote publishing/pushing are not authorized. The user has also asked that no project files change without their approval.
- Completed (Phase 2): character creation/editing/search, Adult/Teen/Child categories, notes and timestamps; multiple JPEG/PNG/WebP photos, labels, primary photo, thumbnails and full-size preview; reusable groups and memberships; archive/restore and explicit permanent deletion.
- Completed (review refinements, 2026-10-10): round avatars with per-photo thumbnail framing (drag/zoom editor); two-column profile form and compact photo cards; group chips, member avatar stacks, single primary "+ New group", footer actions in the group editor, create-closes-editor; sidebar icons; filter-row alignment; refresh keeps the current page/tab/profile/group via hash routes.
- Persistence: schema `0003_photo_framing` (additive; existing photos get default framing). Private originals and thumbnails stay outside Git. Revisions reject stale writes. Interrupted uploads and locked deletions have durable cleanup records.
- Verification: `uv run --locked pytest` — **49 passed**; `uv run --locked ruff check .` — passed; TypeScript/Vite production build — passed. Browser QA of every refinement on an isolated synthetic data folder (port 8766), including a real 0002→0003 upgrade, framing save, group flows, refresh routing, 375px width, no console errors.
- Review records: the user's checklist/report live in `Phase_Checks/` (local only, ignored by Git).
- Runtime: normal studio at http://127.0.0.1:8765 (user restarted it; running schema `0003_photo_framing`); external data `%USERPROFILE%\Character-Studio-Data`.
- Blockers: none.
- Costs: no paid AI clients, credentials, external generation or image transmissions. No dependencies added.
- Pending: further user feedback on Phase 2, if any. Phase 3 (scenes/analysis) requires explicit approval. Backup/restore UI and scene/generation workflows remain later-phase work.
- Git: use `git log -5 --oneline` and `git status --short` for the exact commit/worktree. History rewritten before publishing (noreply email, D011). GitHub repository `CyberSecurityChuck/Character-Studio` created **private** on 2026-10-10 and `main` pushed (remote `origin`). The user will switch it to public themselves; afterwards, ask before enabling secret scanning, push protection and private vulnerability reporting. Dependabot alerts are on. Push only `main`. CI (`.github/workflows/ci.yml`) runs **on request only** (`gh workflow run CI`), typically at phase checkpoints; the first run passed on 2026-10-10.
- Public release prep (2026-10-10): public README with diagrams and demo screenshots, User Guide, MIT licence, Responsible Use, Security policy, CI with privacy guard (D011).

- Planning change (2026-10-10, user-directed, docs only): D009 "CLI bridge first, manual bridge as fallback" — Claude Code CLI for analysis/polish, Codex CLI for generation, manual bridge as fallback. PLAN.md v2.1 adds Phase 2.5 (engine verification spike) and updates Phases 3–5. The user's follow-up decisions on the plan's open questions are recorded in D009 (both CLI analysis engines in Phase 3; content-only approvals; distinct job statuses; paid API engines planned post-MVP). Batch processing planned as Phase 5.5 with a queue-ready job runner from Phase 3 (D010). No application code changed.
- Phase 2.5 (engine verification spike): **approved** ("Approve Phase 2.5", 2026-10-10) and **completed** 2026-10-10. claude 2.1.296 (Pro, signed in by the user) and codex-cli 0.162.1 (ChatGPT) are confirmed. Claude analysis took 49 s and Codex analysis 52 s; both returned valid JSON and were confined to their job folders. Codex generation with 2 reference photos took 72 s, output in `~\.codex\generated_images\<thread_id>\`; the user judged the likeness "clearly me". The official OpenAI docs do not promise identity preservation. The spike gate is met. Details and implementation notes are in `docs/PROVIDER_FINDINGS.md`; test files are in `%USERPROFILE%\Character-Studio-Data\spike-2.5\` (outside Git). **Phase 3 is not approved.**

## Pending: making the GitHub repository public (deferred by the user, 2026-10-10)

The repository stays **private** for now, by the user's choice. When the user decides to publish:

1. ~~**User, on GitHub:** Settings → Emails → tick "Keep my email addresses private" and "Block command line pushes that expose my email".~~ **Done by the user on 2026-10-10.** (Without these, website edits sign commits with the personal Gmail, as happened earlier that day.)
2. **User:** review the repository, then switch it to public (repo Settings → General → Danger Zone → Change visibility).
3. **Assistant, with the user's OK:** enable secret scanning, push protection and private vulnerability reporting (free only for public repositories; `SECURITY.md` already links to the reporting form). Dependabot alerts are already on.
4. **Before going public, re-check:** no personal email in `main` history (`git log --format='%ae%n%ce' | grep -i gmail` should print nothing), and the privacy guard passes (`gh workflow run CI`).

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
