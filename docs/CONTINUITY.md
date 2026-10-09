# Development continuity

## Session start

1. Read PLAN.md and AGENTS.md; read current status/handoff and relevant changelog/decisions.
2. Check `git status --short`, `git log -5 --oneline`, and actual changed files (including untracked files).
3. Compare implementation, migration and dependency state against the recorded checkpoint.
4. Treat uncommitted changes as potentially unfinished or user-owned work. Do not overwrite, reset or clean them automatically.
5. Summarize verified state and the next task within approved scope. A resume request does not authorize a new phase, destructive action or paid operation.

## Milestone / pause checklist

1. Inspect changed files and finish a coherent unit of work where feasible.
2. Run relevant tests. Record exact commands/results and any checks not run.
3. Update PROJECT_STATUS.md (short current view) and SESSION_HANDOFF.md (precise continuation record).
4. Update CHANGELOG.md for meaningful changes and DECISIONS.md for architectural choices, including approval status.
5. Include the timezone, schema revision, runtime/lockfile state, unresolved issues, next action and approval boundaries. Prefer atomic replacement of each document.
6. Inspect staged paths/diff for secrets/private files, then create an authorized local checkpoint commit. Verify the commit actually exists and check the remaining worktree.
7. A document in a commit cannot contain that commit's own hash. Label a referenced hash "last verified implementation commit", or identify the current checkpoint through verified `git log`; never claim a circular self-hash.

Unexpected interruption: the last checkpoint may be stale. Actual files, diffs and tests determine what exists. Preserve work, reconcile the documents, and request clarification only before destructive recovery.

## Fresh-conversation acceptance exercise

In a genuinely new conversation attached to this folder, say:

> Resume Character Studio. Verify the repository against its continuity files, report the current phase and tests, and identify the next permitted action. Do not begin Phase 2.

Pass criteria: the new session independently identifies the current commit/worktree, Phase 1 state, no-paid-API constraint, actual verification evidence, pending work and the Phase 2 approval gate without needing the old chat.

A same-session document audit can validate completeness but is not evidence that this fresh-conversation exercise actually ran. Record that distinction in the handoff. Do not create another user-owned conversation just to claim this acceptance result.
