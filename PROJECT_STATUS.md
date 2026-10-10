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
- Git: local checkpoint for the review refinements; use `git log -5 --oneline` and `git status --short` for the exact commit/worktree. No remote configured; nothing pushed.

- Planning change (2026-10-10, user-directed, docs only): D009 "CLI bridge first, manual bridge as fallback" — Claude Code CLI for analysis/polish, Codex CLI for generation, manual bridge as fallback. PLAN.md v2.1 adds Phase 2.5 (engine verification spike) and updates Phases 3–5. The user's follow-up decisions on the plan's open questions are recorded in D009 (both CLI analysis engines in Phase 3; content-only approvals; distinct job statuses; paid API engines planned post-MVP). Batch processing planned as Phase 5.5 with a queue-ready job runner from Phase 3 (D010). No application code changed; Phase 2.5 is **not approved** — wait for "Approve Phase 2.5".

PLAN.md's original Planning/Not Started header is historical; requirements changed only by the dated v2.1 revision.
