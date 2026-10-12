# Character Studio operating instructions

- PLAN.md is authoritative. Read it before major work; never silently change requirements.
- At every session start read PROJECT_STATUS.md and SESSION_HANDOFF.md, then relevant DECISIONS.md and CHANGELOG.md entries.
- Inspect actual files, `git status --short`, and recent commits before editing. Reconcile stale documentation with reality; preserve user changes.
- Phases 1 and 2 are approved (2026-10-09, Asia/Kolkata; explicit "Approve Phase 2"). Phase 2.5 and Phase 3 are approved (2026-10-10; explicit "Approve Phase 2.5" and "Approve Phase 3"). Phase 4 is approved (2026-10-11; explicit "Approve Phase 4"). Phase 5 is approved (2026-10-11; explicit "Approve Phase 5"). Phase 5.5 is approved (2026-10-11; explicit "Approve Phase 5.5"). Phase 6 is approved (2026-10-11; explicit "Approve Phase 6"), delivered as sub-steps 6A–6D (D022) and accepted after review (6A + 6B and 6C + 6D, 2026-10-12); do not start Phase 7 or work beyond the PLAN.md Phase 6 list without explicit approval.
- The user prioritizes avoiding additional API charges. Per DECISIONS.md D009, AI work runs through the official `claude` and `codex` CLIs on the user's own subscriptions, each run started by a user action and never retried or launched automatically. Never read or store their logins; no third-party gateways, unofficial endpoints or website automation. API engines are approved for building in Phase 6 (D022): off by default, keys entered only by the user in the studio, every paid run confirmed by the user in the studio. The assistant never makes paid calls or handles real keys.
- Keep private images, databases, exports, logs, credentials and backups outside this repository. Never stage them.
- Keep changes incremental. Run relevant tests and report actual results; never invent passing checks or commits.
- At meaningful milestones, before pauses, after significant blockers, and on "Checkpoint Character Studio", update status and handoff atomically where practical. Update changelog/decisions when relevant.
- Record unfinished changes, commands, failures, exact next action and approval scope. Local milestone Git commits are authorized by the Phase 1 approval; remote pushes and history rewriting are not.
- Before a checkpoint commit inspect its staged diff for secrets and private data. Never discard uncommitted work without permission.
- Ask the user before creating or connecting a GitHub repository or pushing code. Confirm the intended GitHub account and repository; local checkpoint approval does not authorize publishing.
- On "Resume Character Studio", verify documentation against files, Git status and history; report discrepancies and continue only within approved scope.
- Keep development recovery separate from application recovery. Persist application state server-side; never automatically repeat interrupted generation requests.
- Run `uv run --locked pytest`, `uv run --locked ruff check .`, and `npm --prefix frontend run build` for relevant changes. See docs/USER_GUIDE.md for setup and launch.
