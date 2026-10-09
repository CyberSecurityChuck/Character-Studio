# Character Studio operating instructions

- PLAN.md is authoritative. Read it before major work; never silently change requirements.
- At every session start read PROJECT_STATUS.md and SESSION_HANDOFF.md, then relevant DECISIONS.md and CHANGELOG.md entries.
- Inspect actual files, `git status --short`, and recent commits before editing. Reconcile stale documentation with reality; preserve user changes.
- Only Phase 1 is approved (2026-10-09, Asia/Kolkata). Do not start Phase 2 or later without explicit approval.
- The user prioritizes avoiding additional API charges. No paid AI calls, API-key setup, unofficial endpoints, or unattended Codex generation integrations.
- Keep private images, databases, exports, logs, credentials and backups outside this repository. Never stage them.
- Keep changes incremental. Run relevant tests and report actual results; never invent passing checks or commits.
- At meaningful milestones, before pauses, after significant blockers, and on "Checkpoint Character Studio", update status and handoff atomically where practical. Update changelog/decisions when relevant.
- Record unfinished changes, commands, failures, exact next action and approval scope. Local milestone Git commits are authorized by the Phase 1 approval; remote pushes and history rewriting are not.
- Before a checkpoint commit inspect its staged diff for secrets and private data. Never discard uncommitted work without permission.
- On "Resume Character Studio", verify documentation against files, Git status and history; report discrepancies and continue only within approved scope.
- Keep development recovery separate from application recovery. Persist application state server-side; never automatically repeat interrupted generation requests.
- Run `uv run --locked pytest`, `uv run --locked ruff check .`, and `npm --prefix frontend run build` for relevant Phase 1 changes. See README.md for setup and launch.
