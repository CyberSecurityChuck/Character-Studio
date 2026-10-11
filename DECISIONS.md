# Architecture decisions

## D001 — Manual bridge first (2026-10-09)

- Decision: keep additional API costs at zero in the initial application; build provider contracts without network-backed AI implementations in Phase 1.
- Reason: user explicitly prioritizes avoiding additional API charges.
- Alternatives: separately billed image/vision APIs; unverified local model; subscription-backed analysis integration.
- Consequence: later MVP export/import is user-assisted. Codex chat tools are not assumed callable by FastAPI. Built-in usage still consumes plan allowances.
- Approval: explicit user preference and Phase 1 approval.
- Status (2026-10-10): superseded as the main approach by D009. The manual flow (copy instruction, export package, import result) is retained as the fallback.

## D002 — Local modular monolith (2026-10-09)

- Decision: React/TypeScript/Vite, FastAPI/Pydantic, SQLAlchemy/Alembic with SQLite, local filesystem assets; one local service serves the built UI.
- Reason: matches PLAN.md; SQLAlchemy/Alembic support the specified relationships and migration requirements.
- Alternatives: PostgreSQL, microservices, Redis/Celery, desktop wrapper.
- Consequence: single-user, loopback-only application; add infrastructure only when demonstrated need warrants it.
- Approval: recommended in Phase 0 and included in approved Phase 1.

## D003 — Separate private storage and source (2026-10-09)

- Decision: configurable absolute data directory, default `%USERPROFILE%\Character-Studio-Data`; reject repository-contained or overlapping storage. Store asset paths relative to that root.
- Reason: private files must remain outside Git and survive source checkout changes. Launcher testing exposed Windows package redirection of LOCALAPPDATA; the user-profile path stays consistent between Codex and Explorer.
- Alternatives: repository-local data, absolute per-asset paths.
- Consequence: application-data backups are separate from Git checkpoints. Test data uses isolated temporary directories.
- Approval: PLAN.md requirement; default location is a Phase 1 implementation detail.

## D004 — Persistence and recovery boundaries (2026-10-09)

- Decision: versioned migrations and transactional settings now; schema/contracts for future approval and job workflows, with implementations deferred to their phases.
- Reason: verify durable foundations without prematurely implementing scenes or generation.
- Consequence: future jobs must persist before dispatch, support unknown outcomes, and never retry automatically; future approval snapshots must bind exact inputs.
- Approval: follows PLAN.md and the approved phase scope.

## D005 — Reproducible development and checkpoints (2026-10-09)

- Decision: uv-managed Python 3.12, project virtual environment and uv lockfile; npm lockfile; local Git milestone commits including continuity records.
- Reason: system Python launcher was not usable; a standalone runtime avoids dependence on Codex's bundled Python.
- Consequence: dependency installation needs network/cache access; normal startup does not download packages or call AI providers. No remote repository is configured.
- Approval: user approved Phase 1 dependency installation and Git checkpoint practices.

## D006 — Windows tooling compatibility and test client (2026-10-09)

- Decision: npm scripts call package JavaScript entrypoints with Node directly; use HTTPX2 for the installed Starlette test client.
- Reason: generated Windows npm command shims misparsed the ampersand in this project's directory. Starlette emitted a deprecation warning for its older HTTPX fallback.
- Alternatives: rename the user's directory; keep obsolete test-client dependencies.
- Consequence: no directory rename or global settings change; lockfiles capture installed versions. Package scripts and tests now pass.
- Approval: routine compatibility fixes within the approved Phase 1 implementation.

## D007 — Local Character Library and file consistency (2026-10-09)

- Decision: add Phase 2 with one additive Alembic migration, generated asset keys, unchanged originals, metadata-free thumbnails, bounded raw-body uploads and no new dependencies.
- Reason: build the approved local library while keeping personal images outside source and avoiding AI charges. Raw image uploads avoid an extra multipart dependency and temporary spool files.
- Decision: serialize writes before reading revisions. Journal upload paths before writing and clear the journal in the metadata transaction; queue deletions transactionally and retry unfinished cleanup on startup.
- Consequence: only committed references are served. Failed batches retain earlier successful photos. An uncertain browser response requires reload before retry; no automatic resubmission. Single local service per data directory remains the operating model.
- Decision: archive is reversible and retains memberships/photos; permanent deletion is explicit. There is currently no generation history. Later history must restrict referenced deletion or preserve immutable snapshots, never cascade history away.
- Approval: explicit "Approve Phase 2"; Phase 3 and AI operations remain unapproved.

## D008 — Phase 2 review refinements (2026-10-10)

- Decision: store avatar framing per reference photo as display metadata (focus point x/y in 0–1 and zoom 1–4) via additive migration `0003_photo_framing`; render it with CSS percentages so one frame matches every avatar size.
- Reason: the user wanted to choose the visible area of round thumbnails. Re-cropping files would alter or duplicate private images; metadata keeps originals and stored thumbnails unchanged.
- Alternatives: server-side cropped avatar files; a single per-character crop (lost when the primary photo changes).
- Decision: hash routes plus `history.replaceState` preserve the current page, library tab and open profile/group across browser refresh, with no backend fallback route and no new history entries.
- Alternatives: path routes (needed a server SPA fallback and restart); pushState history (needed Back-button unsaved-edit guards).
- Decision: short single-purpose forms (group editor) use a footer action bar (destructive left; Cancel/primary right). The long, multi-section character profile keeps Close at top-right so leaving never requires scrolling past Archive/Delete.
- Decision: the user's local review checklists/reports in `Phase_Checks/` stay out of Git (`.gitignore`).
- Approval: user-requested Phase 2 review changes on 2026-10-10 within the approved Phase 2 scope; Phase 3 and AI operations remain unapproved. No dependencies added.

## D009 — CLI bridge first, manual bridge as fallback (2026-10-10)

- Decision: the studio remains the only screen the user works in. Instead of the user carrying files and text to other apps, the studio runs the official command-line tools installed and signed in on this PC, in the background, one user-initiated run at a time:
  - Scene analysis: Claude Code CLI (`claude -p`) on the user's Claude Pro subscription.
  - Optional "Polish prompt": Claude Code CLI on the user's Claude Pro subscription.
  - Image generation: Codex CLI (`codex exec` with its built-in image generation) on the user's ChatGPT subscription.
  - The D001 manual bridge (copy instruction, export package, import result) remains as the fallback, not the main path.
- Replaces D001 as the main approach; D001's manual flow is kept as the fallback for every engine step.
- Reason: stop switching between apps. Both CLIs run on existing subscriptions with no API keys and no per-use billing. Each run still consumes that plan's usage allowance.
- Split: Claude for analysis and prompt polishing, Codex for images only, so the ChatGPT image allowance is spent on images.
- Boundaries: only the official `claude` and `codex` programs, run locally for the user's personal use, signed in by the user. The studio never reads, copies, stores or forwards their login tokens. No extracting subscription credentials into other tools, no third-party gateways (for example OmniRoute), no browser automation or scripting against chatgpt.com or claude.ai. User-supplied findings: Anthropic allows subscription logins only inside Claude Code and Claude.ai; scripted website use breaks OpenAI's terms. See `docs/PROVIDER_FINDINGS.md`.
- Every run is started by an explicit user action (Analyse, Polish prompt, Generate from a valid approval). Never retried automatically; interrupted runs are marked failed/interrupted and not resubmitted.
- Alternatives: manual bridge only (D001; too much app switching); paid OpenAI/Anthropic APIs (per-use billing); third-party subscription gateways or website automation (violate provider terms; rejected).
- Open risk: it is not yet confirmed in practice that Codex's built-in image tool uses attached local reference photos to keep each person's likeness. Phase 2.5 (engine verification spike) records the CLI flags, output locations, timings and failure modes, plus the user's likeness judgement, before Phase 5's Generate button is built on it. The user has stated that OpenAI's documentation confirms reference-photo/identity support, so likeness quality is recorded as a quality check rather than a gate; the manual bridge stays as the fallback either way.
- The optional paid OpenAI API adapter (PLAN.md §12.3) stays off and unchanged.
- Approval: user-directed planning change on 2026-10-10. Planning documents only; no application code changed. Phase 2.5 and Phase 3 require explicit approval ("Approve Phase 2.5").
- Resolved with the user on 2026-10-10 (follow-up to the v2.1 plan):
  - Spike gate: Generate and the CLI analysis engines are built only on mechanics Phase 2.5 confirmed (flags, output locations, failure appearances). The user's likeness verdict is recorded but does not block Generate.
  - The "docs confirm identity preservation" statement stays attributed to the user until Phase 2.5 cites the official OpenAI page.
  - Analysis engines: both Claude CLI (default) and Codex CLI are built and selectable in Phase 3; Codex analysis uses the ChatGPT plan's allowance. Polish prompt stays Claude-only.
  - Approval covers content, not the engine: the same valid approval works for Codex Generate and for manual export, and survives an engine change in Settings. Each job records the engine actually used.
  - Job statuses stay distinct: Failed, Cancelled, Interrupted. Interrupted runs ask the user to check the job folder before retrying. Nothing is resubmitted automatically.
  - The analysis copy of the Base Image has location metadata removed (PLAN §22). Polish prompt uses the same progress/cancel/error handling as Analyse.
  - File access: confine each CLI run to its job folder where Phase 2.5 finds a supported option; otherwise record the limitation and proceed.
  - Future direction: paid API-based engines for both analysis and generation will be offered post-MVP. They are off by default, need separate explicit approval to build, and require per-run cost confirmation. Engine interfaces must allow adding them. AGENTS.md reworded to cite D009 and this boundary.

## D010 — Queue-ready jobs now, batch processing after Phase 5 (2026-10-10)

- Decision: Phases 3–5 build single runs only (one job per click), but all engine runs go through one job runner that executes queued jobs sequentially and whose records support a "Not started" state and an optional batch identifier. Batch processing becomes its own Phase 5.5, moved up from the optional Phase 6 list ("Batch generation", "Multiple image variations").
- Phase 5.5 scope: batch scene creation, "Analyse selected", "Generate approved scenes" (each scene still individually approved), N variations from one approval, optional quick group mapping confirmed per scene.
- Rules: show run count and allowance use before starting; sequential only; single failures continue the batch; usage limit or sign-out pauses it with remaining items "Not started"; Pause/Cancel-remaining always available; no automatic retry or resumption after restart.
- Reason: single runs ship sooner; Phase 2.5 timings and plan limits should inform batch sizes; designing the runner as a queue now keeps the later batch work small. Plan usage limits, not speed, are the main constraint, so pause-and-continue matters more than parallelism.
- Alternatives: batch inside Phases 3 and 5 (bigger phases, later single-run delivery); leave in Phase 6 (risk of restructuring a single-run job system).
- Approval: user-directed planning change on 2026-10-10. Phase 5.5 needs its own explicit approval.

## D011 — Public GitHub repository and public-facing documentation (2026-10-10)

- Decision: publish the project as the public repository `CyberSecurityChuck/Character-Studio` (account and name confirmed by the user). Push only `main`; never push backup branches or other local refs.
- Privacy before first push (explicitly approved history rewrite, nothing previously pushed): all 9 local commits were rewritten to use the GitHub noreply address `174940690+CyberSecurityChuck@users.noreply.github.com`, and the local Windows profile path was replaced with `%USERPROFILE%` in `SESSION_HANDOFF.md` across history. Content otherwise identical. A local-only backup branch `backup/pre-public-rewrite` keeps the original history. The repository's Git config uses the noreply address for future commits.
- Licence: MIT, copyright "CyberSecurityChuck" (handle rather than real name, for privacy).
- Docs: new public `README.md` (badges, Mermaid diagrams checked in light and dark themes, screenshots of fictional demo characters with illustrated portraits). The former README moved to `docs/USER_GUIDE.md`. Added `RESPONSIBLE_USE.md` (consent, children, no deception, provider terms) and `SECURITY.md` (private vulnerability reporting).
- CI: GitHub Actions runs pytest, Ruff and the frontend build on Windows, plus a privacy guard that fails if images, databases, logs, archives, keys or env files are tracked. The only exception is README screenshots in `docs/images/`, which `.gitignore` now allows.
- Alternatives: keep the Gmail address public (rejected for privacy and spam); publish a single squashed commit (loses history); no licence (prevents reuse).
- Approval: user request on 2026-10-10. Creating the GitHub repository, pushing and changing its security settings each need the user's final confirmation.
- Update (2026-10-10): the repository was created **private** first at the user's request; the user switches it to public. CI changed to **on request only** (`workflow_dispatch`) to save Actions minutes while private; run it at phase checkpoints so the README badge reflects a recent check. Alternatives considered: run on every push (truthful but uses minutes); run once then disable (rejected: the badge would stay "passing" forever without re-checking).

## D012 — Phase 3 implementation choices (2026-10-10)

- Decision: one analysis format. The Phase 2.5 JSON Schema is passed to `claude --json-schema` and `codex exec --output-schema`, and the same shape is enforced by Pydantic models (with size limits) for every engine result and every manual import. Pasted manual replies may be wrapped in a Markdown fence or a sentence.
- Decision: analyses are immutable versions. Corrections and confirmed uncertainties create a new `user_edit` version that records the version it was based on; confirmed items are kept beside the schema-strict JSON. Restoring an old version creates a new version.
- Decision: the studio's own template builds the prompt (engine-neutral; Phase 5 adds the Codex wrapper). Prompt versions record the analysis they were built from, so the UI can warn when the analysis has moved on.
- Decision: one `engine_jobs` table and one `JobRunner` thread for all engine runs (analysis now; polish and generation later), claiming the oldest `not_started` job atomically. Statuses: not_started, running, completed, failed, cancelled, interrupted, plus `batch_id` (D010). At startup running jobs become interrupted and waiting jobs cancelled; nothing resumes.
- Decision: launch hygiene. Remove `CLAUDE*`, `ANTHROPIC*`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `CODEX_API_KEY` from the child environment so a run can only use the user's own subscription login and official endpoint (no per-use billing). Check sign-in before each run. Kill the whole process tree on cancel or timeout (`taskkill /T` on Windows).
- Decision: on Windows an npm `.cmd` shim is not executed (cmd.exe would re-parse the prompt). The studio runs the package's own launcher script (`@openai/codex/bin/codex.js`, or Claude Code's `cli.js` if installed via npm) with node, so arguments are passed exactly. Native executables (the current `claude.exe`) run directly.
- Decision: status checks keep only installed / version / signed in / plan; raw status output is never returned or stored.
- Decision: test-only `Settings.engine_commands` replaces the CLIs with `tests/fake_cli.py`; it is not read from the environment.
- Alternatives: separate per-engine schemas (drift risk); overwriting analyses in place (loses provenance); one thread per job (conflicts with sequential plan-limit-friendly runs); running `codex.cmd` through cmd.exe (argument injection risk).
- Approval: within the approved Phase 3 scope ("Approve Phase 3", 2026-10-10). No dependencies added.

## D013 — Phase 3 review refinements (2026-10-11)

- Decision: common actions are available on cards via a ⋯ menu (keyboard: arrow keys, Escape) and a Select mode with a selection bar, on Scenes, Characters and Groups. The detailed screens keep their own buttons.
- Decision: bulk actions call the existing single-item endpoints one by one with each item's revision, continue past individual failures and report them by name. Scenes with a running analysis are skipped. No new bulk endpoints, so every safety check stays in one place.
- Decision: field explanations in settings use an accessible ⓘ tooltip (hover, focus or click; Escape closes) instead of permanent helper text.
- Decision: sentence case for analysis text is applied at display time only, so stored analyses remain exactly as the engine or user wrote them.
- Alternatives: server-side bulk endpoints (more code paths to secure); rewriting stored text to sentence case (alters provenance).
- Approval: user's Phase 3 review report and "Yes, please go ahead with the fixes" (2026-10-11), including the Characters and Groups card options.

## D014 — Phase 4 mapping, approval and polish choices (2026-10-11)

- Decision: subjects (labels and boxes) stay inside the versioned analysis rather than a separate SceneSubject table (PLAN §20 allows refinement). Correcting boxes, adding or removing a subject creates a `user_edit` analysis version. Labels never renumber, so an assignment cannot silently move to another person.
- Decision: `subject_mappings` rows are keyed by scene and subject label and record a fingerprint of the subjects (labels and boxes) they were confirmed against. A new engine or manual analysis changes the fingerprint, so the user must check and save the assignments again; the user's own box edits carry confirmed assignments forward. Subjects without a row are undecided. Approval needs every subject decided.
- Decision: one character per subject per scene (identity separation). Characters without photos cannot be assigned; archived characters cannot be newly assigned but existing assignments stay valid. A group is stored per scene only to narrow the pickers.
- Decision: reference selection is stored at save time (automatic: primary, then the viewpoint closest to the subject's face angle, then distinct viewpoints, up to 3; manual: 1–4 in the user's order). New library photos never change a saved selection. Image numbers follow subject order, then photo order. Provider reference limits are unverified, so more than 4 photos in total only shows a note.
- Decision: character names never enter the prompt; identities are referred to only by "Subject N" and image numbers.
- Decision: prompt versions record the assignments they were built for (`mapping_hash`, over actions, characters and photo order, not boxes). A required-element check (each replaced subject named with all its image numbers in one sentence; each kept subject named with keep/unchanged; no image numbers above the attached count) is shared by the review screen and polish acceptance.
- Decision: approvals are immutable snapshots of their inputs (Base Image path and hash, analysis id/version/hash, subjects fingerprint, prompt id/version/text/negative/polished flag, each subject's action, character and reference photo ids, hashes and image numbers, empty generation settings). Validity is recomputed, not trusted: after every change, after library deletions and at startup the studio rebuilds the snapshot; any mismatch sets `invalidated_at` and a readable reason, keeping the record. Names are display-only and not hashed, so renaming is harmless. Approving re-hashes the Base Image and reference files on disk. Approval covers content, not the engine (PLAN §11). Phase 5 must call `workflow.require_valid_approval`.
- Decision: blockers (undecided subjects, unconfirmed analysis details, missing photos, no saved prompt, a running job) prevent approval; warnings (prompt built for an older analysis or other assignments, missing required elements) need an explicit "I checked these" tick.
- Decision: Polish prompt is an engine job of kind `polish` on the Claude CLI only, text only (`--tools ""`, `--restricted`), on the saved latest prompt version. The candidate is stored with the job (`output_text`); only "Use polished" creates a prompt version (`is_polished`, `polished_from_version_id`, engine version). Keep original records the decision. A polish candidate for an older prompt is no longer offered.
- Decision: deleting a character sets its subjects to undecided and deleting a photo removes it from assignments (refilling automatic selections), and both cancel affected approvals; snapshots are kept. Deleting a scene deletes its assignments and approvals.
- Decision: the workspace opens on the step its saved stage suggests and then stays on the step the user chose.
- Alternatives: a separate subjects table with renumbering (assignments could follow the wrong person); dynamic automatic reference selection at approval time (adding a library photo would cancel approvals unexpectedly); trusting a stored "valid" flag (misses offline changes); names in the prompt (privacy, and risk of the model matching a public figure).
- Approval: "Approve Phase 4" (2026-10-11). Schema `0005_mapping` is additive. No dependencies added.

## D015 — Phase 4 review fixes (2026-10-11)

- Decision: the required-element check treats "Subject N's identity comes only from Image …" as its own required element. A sentence linking the subject to all its image numbers must also contain "only"; the attached-images list alone no longer satisfies the check. Polish rules name this instruction explicitly.
- Decision: prompt versions may be deleted. Refused for the version a valid approval uses ("withdraw the approval first") and for a version being polished. Deleting the current version makes the previous one current (or brings back a template draft). Approval snapshots keep their own copy of the prompt, so history stays complete. New version numbers skip any number an approval recorded, so approval history never points at two different prompts with the same number.
- Decision: the version list moves from a dropdown into a Version history dialog with a list, preview and footer actions (Delete left; Close and Load into editor right), matching the studio's dialog pattern.
- Decision: subject boxes get eight resize handles on the selected box only, to keep the image readable; each handle moves only its own sides, with a 2% minimum size.
- Alternatives: soft-deleting prompt versions (needs a schema change; snapshots already preserve approved text); renumbering versions after deletion (breaks references in approvals and polish runs).
- Decision (follow-up check, 2026-10-11): the polish comparison diffs lines first and then words only within changed passages (whitespace and wrapping ignored), with a 16-bit table and a limit of 12 million cells per comparison. Only a passage beyond that limit is marked as a whole, with a note. A word-count summary sits above the columns. Reason: the earlier single word-level table gave up on real prompts of about 1,300 words, so nothing was marked.
- Approval: user's Phase 4 review report and "Yes, please go ahead with all four fixes" (2026-10-11); follow-up report request to show the polished prompt's differences. No schema change, no dependencies added.

## D016 — Phase 5 generation, manual bridge and results (2026-10-11)

- Decision: generation is an engine job of kind `generation` on the existing runner (D012), with the approval id in `input_id`, the mode in `settings_json` and Codex's thread id in `provider_request_id`. `require_valid_approval` runs in the transaction that queues it; the runner re-checks that the same approval is still current before building anything and otherwise fails with "nothing was sent".
- Decision: everything sent or exported is built from the approval snapshot, not the live scene: Base Image and reference photos are found by the snapshot's paths and ids and must match its content hashes, the prompt and negative prompt are the snapshot's copies. Images become numbered, upright, metadata-free JPEGs (`image-<n>.jpg`, the same numbers the prompt uses). Text files are written with `\n` exactly as approved.
- Decision: the Codex wrapper is fixed studio text around the approved prompt: use built-in image generation for exactly one image, run no commands, touch no files, the attachment order, the brief, the things to avoid, and "reply with only the full path". Variation adds one fixed line (small natural differences in fine details; never composition, poses, outfits or identities). The instruction is one argument, so runs above 24,000 characters are refused with a pointer to Export for manual use.
- Decision: success only when the final message names an existing image inside `<CODEX_HOME or ~/.codex>/generated_images/<thread_id>/` that decodes (Phase 2.5). The folder is not scanned on a normal run. Paths are removed from the final message before looking for sign-in or limit wording, so digits in a path cannot be mistaken for an error code. Only the user-started "Look for a saved image" lists that one thread's folder, for runs that failed, were cancelled or were interrupted; images already kept for that job (same hash) are skipped.
- Decision: approval snapshots keep `settings: {}`. Codex exposes no confirmed size or quality options, so there is nothing to lock; changing this later would need a new snapshot version, not a silent change. Approval still covers content, not the engine.
- Decision: manual exports are `engine_jobs` rows of kind `export` (engine `manual`, completed at creation) with their folder and a zip; imports link to the chosen package's approval even if it has since ended (honest provenance), or else to the current valid approval; an import without either is refused. The user's "Made with" text is stored as given. Export packages include character names in `mapping.txt`; the Codex run folder never does.
- Decision: results (`generation_results`) are separate files under `generations/` with metadata-free thumbnails, written with the same path journal as uploads, numbered per scene and never replaced. One preferred result per scene. Deleting a result or scene removes its files through the deletion queue; deleting a character or photo keeps results and approvals.
- Known limitation: copies of reference photos inside earlier generation and export packages stay in the scene's run folders after the character or photo is deleted, until the scene is deleted. Reported to the user for a decision.
- Not built: the optional paid OpenAI API adapter listed in PLAN.md Phase 5 stays disabled, as AGENTS.md and D009 require separate explicit approval for paid API engines. The provider and job design leaves room for it.
- Alternatives: a separate generation job table (would split the queue that Phase 5.5 batches rely on); building packages from the live scene (could send unapproved inputs); scanning Codex's whole output folder (could pick up another run's image); storing a pseudo-status such as "waiting for import" (needs a constraint change; it is derived from the import count instead).
- Approval: "Approve Phase 5" (2026-10-11). Schema `0006_generation` is additive. No dependencies added.

## D017 — Package copies on deletion, and backups (2026-10-11)

- Decision (user direction): deleting a character or photo never removes its copies in saved packages automatically. When copies exist, a pop-up states how many, in which packages and scenes, and offers Delete and remove copies, Delete and keep copies, or Cancel. `DELETE` endpoints take `remove_copies` (default false); `GET /api/package-copies` reports the counts.
- Decision: copies are found from each package's approval snapshot (photo id → image number), so no new tracking table is needed. Removal queues the copies and each affected export's zip in the durable deletion queue inside the same transaction as the deletion; afterwards the zip is rebuilt from the remaining files, the README notes the removal, and a deleted character's name in `mapping.txt` becomes "Deleted character". Codex run folders never contain names. Results, approval snapshots and Base Images are untouched.
- Decision (user: "it should come now, but I leave the decision to you"): backup and restore are part of Phase 5, as PLAN.md §22 and docs/RECOVERY.md require before the MVP is complete.
- Decision: a backup is one zip with a SHA-256 manifest. Consistency comes from one write transaction in which the database is copied with SQLite's backup API (through a separate read-only connection; backing up from the locked connection itself blocks forever) and every asset file is hard-linked into a snapshot folder (copied if linking fails). The zip is written from the snapshot after the lock is released, so writes are blocked only briefly and later deletions cannot break the backup. Rejected: holding a lock for the whole zip (blocks the studio), deferring deletions during a backup (would rebuild export zips with photos the user had just asked to remove).
- Decision: restore runs only while the studio is stopped, via `Restore-Studio.cmd` / `python -m backend.backup restore`. It verifies everything into a new folder first and swaps folders by renaming; the previous data folder is kept as `<name>.before-restore-<time>` and its `backups` folder moves across. No in-app restore button: replacing an open database from inside the running service is not safe.
- Not included in backups: the `backups` folder, logs, the launcher's process record and folders the studio does not manage. Optional encrypted backups remain a Phase 6 item.
- Approval: the user's answers on 2026-10-11, within Phase 5. No schema change, no dependencies added.

## D018 — Phase 5 review fixes (2026-10-11)

- Decision: run time is derived from each engine job's `started_at` and `finished_at`, so no schema change. Results show it only for a normally completed Codex run (imported and recovered results were not timed by the studio). The average shown on the Generate step covers completed generation runs on this PC; it is a planning aid for Phase 5.5, not a promise.
- Decision (user's choice): "preferred" is a favourite mark; a scene may have any number of preferred results. This replaces D016's one-per-scene rule.
- Decision: result selection follows D013: ⋯ menu per card, Select mode with a selection bar, bulk actions calling the single-result endpoints one by one and reporting failures by name. One selected image downloads as itself; several come as one zip built in `exports/` and deleted after it is sent.
- Approval: the user's Phase 5 review report and the answers "Several per scene" and "Yes, go ahead" (2026-10-11).

## D019 — Phase 5 follow-up fixes (2026-10-11)

- Decision: the average generation time describes past Codex runs, so it is shown whatever the current generation engine is.
- Decision: row actions in Backups and Manual packages are compact secondary buttons with a line icon (`Glyph` in `Controls.tsx`), destructive ones with the red outline, replacing text links.
- Decision: a manual package can be deleted. Its folder goes through the deletion queue and its job record is removed. Results imported from it are kept and remain linked to their approval snapshot (their exact inputs); their `job_id` is cleared, so only the package link is lost. Downloaded copies are outside the studio's control and the confirmation says so. Package numbers come from the remaining folders, so a later package may reuse a deleted package's number.
- Approval: the user's follow-up report and "Yes, go ahead" (2026-10-11).

## D020 — Phase 5.5 batch processing (2026-10-11)

- Decision: a batch is a `batches` row (kind, engine, status, pause reason, settings) plus ordinary `engine_jobs` sharing its `batch_id` and ordered by a new `batch_position`, as D010/D012 planned. Every item is a full job record from the start, so "every item keeps its own job record" holds even for items that never run. Status records intent only (running, paused, cancelled); done / failed / not started are derived from the items.
- Decision: the runner claims a batch item only while its batch is running, and single clicks go before waiting batch items, so a quick single analysis is not stuck behind a long generation batch. Runs stay strictly one at a time.
- Decision: pausing. Usage limit, signed out and (extension of the plan) not installed pause the item's batch and every other running batch on the same engine, because each following item would fail the same way. A sign-in or install problem found by the pre-run check puts the item back to not_started (nothing was sent); a limit reported by Codex marks that item Failed. Pause by the user lets the run in progress finish. Continue checks the engine's sign-in first and refuses while it is still signed out. Cancel remaining never kills a run in progress (it may already have used allowance); that run has its own Cancel.
- Decision: restart. Running items become Interrupted, waiting single runs are cancelled as before, waiting batch items are kept and their batches paused ("restart"). Nothing continues without the user.
- Decision: waiting batch items count as active runs, so their scenes cannot be edited or queued again; the stages "Waiting to analyse" and "Waiting to generate" say so, and **Remove from batch** (cancelling that item) frees a scene. Generation items record their own scene's approval when queued and are re-checked when they start, so an approval that ends while waiting means "nothing was sent" for that item only.
- Decision: retries are explicit only: **Try failed again** on a finished batch creates new items that record `retry_of`; failed records are never reused. Interrupted generation items are left to the scene's "Look for a saved image" first.
- Decision: sizes. At most 50 analyses or 20 images per batch, and 1–5 images per scene in a batch (1–10 from one scene's Generate step), because Codex image generation uses limits 3–5 times faster (docs/PROVIDER_FINDINGS.md). Time estimates use the average of finished runs of that kind on this PC.
- Decision: batch scene creation uploads files one by one through the existing endpoint (every file passes the same checks; failures are listed by name); no bulk endpoint.
- Decision: quick group mapping suggests the group's members, in the order the user arranges them, for the scene's subjects sorted left to right by box centre. Suggestions are stored as mappings with `subjects_hash = "suggested"`, which never matches a fingerprint, so approval is blocked until the user confirms by saving the assignments. Approved scenes, scenes without an analysis and (by default) scenes with assignments are skipped; members without photos or archived are left out and reported.
- Alternatives: lazily creating jobs from a separate items table (items that never ran would have no job record); pausing by killing the running process (wastes allowance already used); automatic continuation after a limit resets (forbidden by D010).
- Approval: "Approve Phase 5.5" (2026-10-11). Schema `0007_batches` is additive. No dependencies added.

## D021 — Phase 6 planning notes (2026-10-11, not approved for building)

- User direction: Phase 6 should include every item in the PLAN.md Phase 6 list. It should add an API provider layer, with the Anthropic API, the OpenAI API and other relevant providers that the assistant researches and recommends, beside the CLI and manual engines. The Google Gemini API (free AI Studio key) is the first test provider.
- Finding (Google's pricing and image-generation docs, read 2026-10-11; re-verify at Phase 6 start): Gemini text and vision models are free on the free tier, so a free key can test analysis. Image output is "Not available" on the free tier, so testing generation needs billing and the paid-run rules (§12.3, D009). Gemini image models edit by text instruction with reference images (up to 14 in total, 4–5 of them "character" images depending on the model). They document no mask or inpainting, so region editing and selective replacement would rely on instructions rather than masks. Output carries a SynthID watermark. Gemini 2.5 Flash Image is deprecated and shuts down on 2026-10-02.
- Provider shortlist (assistant's recommendation, accepted by the user for the notes, 2026-10-11; re-verify prices, models and features at Phase 6 start):
  - Analysis: Google Gemini (free tier, for testing), Anthropic Claude API (analysis only; no image generation), OpenAI (vision-capable GPT models).
  - Generation and editing: OpenAI Images API (GPT Image models; several references; mask edits), Google Gemini image models ("Nano Banana"; character references; instruction edits only, billing needed), Google Imagen on Vertex AI (mask edits, to confirm), Black Forest Labs FLUX (Kontext for reference edits, Fill for masked region edits), Stability AI (inpainting, search-and-replace).
  - Optional aggregators: fal.ai or Replicate (one key, many models such as FLUX and ByteDance Seedream). They are intermediaries, so they need the user's explicit OK given the "no third-party gateways" rule.
  - Suggested starting set: analysis with Gemini, Anthropic and OpenAI; generation with OpenAI and Gemini, plus FLUX or Stability AI for region editing and selective replacement.
- Status: notes only. Building needs "Approve Phase 6"; each paid API engine and any paid run also needs the separate approval and cost confirmation already required by D009 and PLAN.md §12.3.

## D022 — Phase 6 approval, delivery in sub-steps, and the API provider layer (6A) (2026-10-11)

- Approval: "Approve Phase 6" (2026-10-11, Asia/Kolkata). The user's answers the same day: deliver Phase 6 in sub-steps 6A–6D, each with its own local commit and Phase_Checks review (6A API provider layer and analysis engines; 6B identity/composition checks, saved presets, comparison view; 6C region editing, selective identity replacement and API image engines; 6D encrypted backups). Build the full starting set of API engines (D021): analysis with Gemini, Anthropic and OpenAI; generation and editing with OpenAI Images, Gemini image models and FLUX (Fill for masks). Stability AI is left out until its pricing and editing pages can be verified. Adding the `cryptography` dependency for 6D is approved. This approval covers building the engines (off by default, no calls made by the assistant). Every paid run still needs the user's confirmation in the studio.
- Facts re-checked at Phase 6 start (2026-10-11; details in docs/PROVIDER_FINDINGS.md): the Gemini free tier still covers text/vision analysis models and no image output; the cheapest paid image model is Nano Banana 2.1; `gemini-2.5-flash-image` shut down on 2026-10-02. OpenAI's edits endpoint takes masks, but the docs say the model may not follow the mask's exact shape. BFL's FLUX.1 Fill [pro] does true mask inpainting and its API is asynchronous (polling).
- Decision (6C design, recorded now): after any region edit, the studio composites only the masked area of the edited image back onto the original, so pixels outside the mask are untouched whatever the provider does.
- Decision (6A): API keys are entered in Studio settings and stored one file per provider in `<data dir>/keys/`, encrypted with Windows DPAPI for the current Windows user (`backend/keystore.py`, standard library `ctypes`, no dependency). The folder is outside the repository and is not in `ASSET_DIRECTORIES`, so it is never backed up. A restore moves it across like `backups`. Keys are write-only from the browser, sent only in their provider's auth header, redacted from saved responses and error text, and never logged.
- Decision (6A): calls use Python's `urllib` against fixed official endpoints (`generativelanguage.googleapis.com`, `api.anthropic.com`, `api.openai.com`). `Settings.api_base_urls` exists only for tests and is never read from the environment. One request per run, in a helper thread so Cancel and the time limit respond at once. Cancel and timeout messages say that a request already received may still be charged. Nothing is retried.
- Decision (6A): analysis sends a ≤1568 px copy of the job's metadata-free `base.jpg` with `MANUAL_INSTRUCTION` (it embeds the schema). Gemini uses JSON response mode, Anthropic a forced tool call with the studio schema as `input_schema`, OpenAI Chat Completions JSON mode. Every reply is validated with the same studio schema. The job folder keeps `request.json` (no key, no image data), `response.json` and `api-image.jpg`.
- Decision (6A): cost confirmation is enforced by the server. Single analyses, analysis batches, Continue and Try failed again on an API batch are refused without `confirm_charges: true`. The dialog states what is sent, to which company, the model, the number of runs, average tokens of earlier runs (recorded per job as `usage`) and a link to the provider's prices. The studio does not hard-code prices. Gemini's free-tier note includes Google's use of free-tier content to improve its products.
- Decision (6A): the model is chosen per engine in Studio settings (`engine_settings.api_models_json`), recorded on the job when it is queued (what the user confirmed is what runs) and stored as the analysis's `engine_version`. "Test key" uses each provider's free model-list endpoint. The only suggested default is `gemini-2.5-flash` (free tier, verified 2026-10-11).
- Decision (6A): new pause kinds `key_problem` and `model_problem` pause API batches like `usage_limit`. HTTP 401/403 or a key complaint → key_problem; 429, quota, credit balance or billing → usage_limit; 404 model → model_problem.
- Decision (6A): migration `0008_api_engines` rebuilds `engine_settings` and `scene_analyses` to widen their CHECK constraints and adds `api_timeout`/`api_models_json`. Migrations now run with foreign keys off (SQLite's documented table-rebuild procedure) and `PRAGMA foreign_key_check` must be clean before commit. `PRAGMA defer_foreign_keys` was tried and rejected: its violation counter does not recover after a drop-and-rename.
- Provider registry: the three API engines are `unverified` until a real run is observed. `paid_operations_enabled` in bootstrap is true once any key is saved.
- Alternatives: the Windows Credential Manager via `keyring` (new dependency; DPAPI gives the same per-user protection); provider SDKs (several new dependencies); keys in the database (would enter backups); strict structured-output modes (the studio schema uses `const`, which some strict modes reject; validation stays local).

## D023 — Phase 6B: quality checks, presets and the comparison view (2026-10-12)

- User direction (2026-10-12): start 6B now and review 6A and 6B together afterwards with one combined checklist. The 6A checklist is on hold.
- Decision: a **quality check** is an engine job of kind `check` (no constraint change: `engine_jobs.kind` has no CHECK) with the result id in `input_id`. It uses the selected analysis engine (Claude CLI, Codex CLI or an API engine). Manual analysis cannot check. It runs once from a user click, with the same cancel, time limit, sign-in, key and charge-confirmation rules as an analysis. A scene with a waiting or running check shows the stage "Checking a result…" and is locked like any other run.
- Decision: the job folder holds the approval's package (`write_package`: numbered metadata-free images, hash-checked against the snapshot) plus the result as the next image number, `instruction.txt` and `schema.json`. CLI runs read the files (Claude `--tools Read --restricted --json-schema`; Codex `-s read-only --disable image_generation` with every image attached by `-i` and `--output-schema`). API runs send each image after an "Image N:" label, with the schema inside the instruction (Anthropic: forced tool `save_quality_check`). The instruction lists each subject's expectation (replaced → the reference image numbers; kept → same person as in Image 1; unassigned → position and pose only), the prompt version's scene changes as intended, and forbids identifying or naming anyone. Character names are never sent.
- Decision: the reply schema has scores 1–5 (0 = could not judge) for seven composition aspects and each subject, short notes, a summary and up to 12 issues. Replies are validated locally (`backend/quality.py`). Results are stored in `quality_checks`, never overwritten; the card and viewer show the **lowest** composition score and the lowest replaced-person score, so a single weak aspect is not averaged away. The UI calls it "a model's opinion of what it can see, not a measurement" (PLAN.md §13).
- Decision: deleting a result deletes its checks and is refused while a check of it waits or runs; deleting a scene deletes its checks. Checks are in backups with the database.
- Decision: **presets** (`generation_presets`) hold a unique name (case-insensitive), scene changes, negative-prompt additions and images per click (1–10). Applying one on the Prompt step fills Scene changes, rebuilds the draft and appends the negative additions line by line without duplicates; the user still saves and approves. On the Generate step (and the generation batch dialog, capped at 5 per scene) it sets the count. The preset's name is recorded in the generation job's `settings_json` and shown on results; deleting a preset leaves those records. Engine, model, size and quality settings join presets in 6C with the API image engines.
- Decision: the **comparison view** (`frontend/src/Compare.tsx`) replaces Phase 5's result/side/slider viewer: Result, Side by side, Slider, Overlay (opacity) and Difference (CSS `mix-blend-mode: difference`), against the Base Image or another result of the same scene, with zoom (fit to 4×) and drag/arrow-key pan shared by every pane, and optional subject boxes from the current analysis. Images whose shape is within 5% of the Base Image fill its frame (so boxes and overlays line up); others are fitted inside it. Selecting 2–4 results of one scene offers **Compare** with all of them next to the Base Image. Everything is local; nothing is sent.
- Refactor: `engines.analysis_command` takes an instruction and image list; `engines.structured_reply` reads any schema run; `api_engines.run_structured` and `StructuredTask` serve analysis and checks. API analysis copies are now named `api-<file>` (`api-base.jpg`).
- Schema `0009_quality` is additive (two tables). No dependencies added.
- Alternatives: computing similarity locally (would need face/embedding models and new dependencies; rejected for now); averaging scores (hides the weak aspect); applying presets directly to saved prompts (would bypass the user's save and approval).
