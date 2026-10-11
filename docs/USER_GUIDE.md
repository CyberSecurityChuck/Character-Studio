# Character Studio — User Guide

A local-first home for reusable characters, reference scenes and approved image workflows. For the project overview, see the [README](../README.md). Commands below run from the project root folder.

**Current scope: Phase 4 Character Mapping and Approval** (complete), on top of Phase 3 Scene Analysis and the Phase 2 Character Library. Add scenes, analyse them, assign saved characters to the people in them, choose reference photos, edit or polish the prompt and approve the exact inputs. Generation and export/import are not implemented yet; PLAN.md defines those later phases. Do not upload personal photographs into the source folder.

**How it works (D009).** The studio stays the only screen you use. When you ask it to, it runs the official command-line tools on this PC in the background: **Claude Code** (`claude -p`, your Claude Pro subscription) analyses a scene and can optionally polish the prompt (you can pick Codex for analysis instead in Settings), and **Codex CLI** (`codex exec` with built-in image generation, your ChatGPT plan) generates the image from an approved prompt. The manual bridge (copy the instruction, export the package, import the result) remains as the fallback. No API keys and no per-use billing; the studio never reads or stores either tool's login.

## Start and stop

After setup, double-click **Start-Studio.cmd**. It starts the local service in the background and opens **http://127.0.0.1:8765**. Double-click **Stop-Studio.cmd** to stop the launcher-managed service. Closing the browser does not stop the service. Save changes before closing; only changes acknowledged as saved are durable.

The launcher refuses to stop a process whose executable/start time no longer matches its record. For terminal development, use `uv run --locked python -m backend` and Ctrl+C instead.

## First setup / clean checkout

Prerequisites: Windows, Node.js 24 LTS with npm, and uv. Python 3.12 is managed by uv; dependencies live in the project's `.venv`. No OpenAI account credentials or API key are required by this application.

For scene analysis (Phase 3) and later AI features: install and sign in to **Claude Code** (`claude`) with a **Claude Pro** subscription, and **Codex CLI** (`codex`) with a **ChatGPT plan that includes image generation (Plus or above)**. Sign in through each tool yourself; the studio only launches them. Without them, the manual bridge still works.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1
```

Setup installs locked Python and npm dependencies and builds the frontend. Package downloads require internet access. Normal startup requires neither downloads nor AI requests. Do not modify lockfiles without recording the dependency change.

Equivalent commands:

```powershell
uv sync --locked --python 3.12
npm.cmd ci --prefix frontend
npm.cmd --prefix frontend run build
uv run --locked python -m backend
```

## Storage and configuration

Default data directory: `%USERPROFILE%\Character-Studio-Data`. The application creates `studio.db` plus directories for characters, scenes, generations, thumbnails, exports and backups. Preferences, character profiles, reference photos, thumbnails and groups persist locally. These files belong to the user and must survive source updates. The user-profile location avoids Windows packaged-app redirection of `LOCALAPPDATA`, so launches from Codex and Explorer use the same default.

Optional environment variables, set before starting:

```powershell
$env:STUDIO_DATA_DIR = 'D:\Character-Studio-Data'
$env:STUDIO_PORT = '8765'
$env:STUDIO_MAX_UPLOAD_BYTES = '20971520' # 20 MiB per photo
```

`STUDIO_DATA_DIR` must be absolute and outside (and not a parent of) the source repository. Changing it opens a different data directory; it does not move existing work. Stop the running service before changing configuration. Use the same environment configuration when stopping it. Do not put the live SQLite database in a shared/network/cloud-sync folder.

The backend always binds to `127.0.0.1`. Host/origin checks, a per-process request token, CSP and no-store responses restrict browser-based misuse. This is a single-user local tool, not a public authenticated service. Local files are not encrypted; anyone with filesystem access can read them. No analytics, remote fonts or AI network clients are included.

## Development

Backend: `uv run --locked python -m backend`.

Frontend in a separate terminal: `npm.cmd --prefix frontend run dev`, then visit `http://127.0.0.1:5173`. Vite proxies `/api` to the local backend. Set the same `STUDIO_PORT` for both processes if changing it. After frontend changes, build again for the normal launcher.

```powershell
uv run --locked pytest
uv run --locked ruff check .
npm.cmd --prefix frontend run build
```

If a restricted agent sandbox prevents uv cache access, use the installed executables for offline checks: `.\.venv\Scripts\python.exe -m pytest` and `.\.venv\Scripts\ruff.exe check .`. An agent should request appropriate escalation for necessary blocked operations rather than change system permissions.

Tests use isolated temporary data outside the repository. They do not call external image services. The database schema is managed by Alembic on startup; unknown future revisions fail rather than being downgraded. Never edit historical migrations after release; add a new revision. Migrations receive an explicit SQLAlchemy connection from `backend/persistence.py`; destructive downgrades are disabled.

## AI capabilities and costs

Scene analysis and prompt polishing run through the official CLIs (Phases 3–4). There is no generation endpoint yet, no credential storage and no automatic retry. Paid API access is **disabled**. Paid API-based engines for analysis and generation are planned after the MVP as an opt-in that needs separate approval and asks for cost confirmation on every run.

Planned direction (DECISIONS.md D009): the studio runs `claude -p` (default) or `codex exec` for scene analysis, `claude -p` for optional prompt polishing, and `codex exec` for image generation, each started by your click, with a timeout, cancel and no automatic retry. The manual bridge (export an approved package to Codex/ChatGPT and import the result) is the fallback. The Phase 2.5 spike verified both CLIs' flags, output locations and failure modes; the studio uses only those flags.

Each run uses your plan's allowance and sends data to that provider: **Analyse** sends the Base Image to Anthropic (or to OpenAI if Codex is the analysis engine); **Polish prompt** sends prompt and analysis text to Anthropic; **Generate** sends the Base Image and chosen reference photos to OpenAI. There is no promise of unlimited generation or perfect likeness/pose preservation. See `docs/PROVIDER_FINDINGS.md`.

## Continuity and recovery

- Open a new Codex conversation **in this project folder** and say **Resume Character Studio**.
- Read AGENTS.md, PLAN.md, PROJECT_STATUS.md and SESSION_HANDOFF.md; compare them with actual Git/files before continuing.
- Say **Checkpoint Character Studio** before a planned pause. See `docs/CONTINUITY.md` for the exact protocol.
- Approval covers Phases 1, 2, 2.5, 3 and 4. Phase 5 and later require explicit approval.

For data recovery and current backup limitations see `docs/RECOVERY.md`. Git backs up source history, not private application data.

## Troubleshooting

- **Cannot reach studio:** run Start-Studio.cmd; check `server.stderr.log` in the selected private data folder. No request bodies are logged.
- **Port in use:** stop the existing instance or select another port; do not kill unrelated services.
- **Session expired after restart:** reload before saving; the per-process request token has changed.
- **Another tab saved first:** the app rejects the stale save and retains your typed edit. Copy it before choosing "Discard local edit and reload".
- **Database revision error:** stop and inspect the error; preserve the data folder. Do not delete or downgrade the database to fix startup.
- **Build missing:** run `npm.cmd --prefix frontend run build`, then restart.

## Character Library

Open **Characters**, choose **New character**, enter a name/alias and age category, then save. Add one or more JPEG, PNG or WebP still photos (20 MiB and 40 megapixels per photo by default). Originals remain unchanged, including their metadata; separate thumbnails omit metadata and correct display orientation. Nothing is sent to an external service.

Use each photo's label selector and **Make primary** button. Open a thumbnail for the full-size preview. To choose what shows inside a character's round thumbnail, click the profile photo (✎) or **Adjust thumbnail** on the primary photo, then drag and zoom; only the display framing is saved and the original photo is unchanged. **Groups** lets you create/rename groups and add/remove members; a character can belong to several groups. Search by name and filter by group or archived status. Each character card and group row has a **⋯** menu (Rename, Archive/Restore or Delete), and **Select** lets you archive, restore or delete several characters, or delete several groups, at once.

Refreshing the browser keeps the current page, library tab and open profile or group (the address shows, for example, `#/characters/<id>` or `#/groups`).

**Archive character** preserves all data and hides the profile from the active list; enable **Show archived** to restore it. **Delete permanently** removes the profile, references and memberships after explicit confirmation. Deleting a group preserves its characters/photos. A deleted primary photo falls back to the oldest remaining reference.

Save profile edits before changing photos. If a batch upload stops, earlier successful uploads remain saved; reload to verify saved state before selecting remaining files. A stale revision or expired session is rejected. Reload after a service restart. Locked file deletions remain queued and are retried at startup; the UI reports pending cleanup.

## Scenes and analysis

Open **Scenes** and choose **+ New scene**. Pick a JPEG, PNG or WebP Base Image (the scene whose pose, framing and light you want to recreate) and optionally a title. The image stays on this computer until you choose to analyse it. Scenes can be renamed, duplicated (the copy takes the current analysis and prompt) or permanently deleted, either inside the scene or from the **⋯** menu on its card. **Select** lets you tick several scenes and delete them together (scenes with a running analysis are skipped). The Overview lists recent scenes and offers **Resume**.

**Analyse with Claude** (or Codex, if selected in Studio settings) sends the Base Image to that company using your own sign-in and plan allowance. It runs once per click with a progress timer and a **Cancel** button; you may leave the page while it runs. Errors (not installed, signed out, usage limit, time limit, unexpected reply) offer **Try again** and **Do it manually**. Nothing is retried automatically. If the studio stopped mid-run, the run shows as **Interrupted**: check the job folder shown before trying again.

**Do it manually** works with any chat app: copy the instruction, attach the Base Image, paste the whole reply back. It is checked against the same format as engine results.

Analyses are saved as versions with their source and CLI version. Details the analysis was unsure about appear under "Please check": **Confirm** keeps them as written; **Correct** opens the editor. Every edit is saved as a new version; earlier versions can be viewed and restored. When the Base Image shows people, "Show subjects" draws their approximate boxes.

The **Generation prompt** is written by the studio from the analysis (numbered images, "Subject N" labels, identity and composition locks, negative prompt). Edit it freely, add **Scene changes** and rebuild, copy it, and **Save prompt version**. Saved versions can be loaded back into the editor. If the analysis changes, the studio offers to rebuild the prompt.

**Studio settings → Analysis and generation engines** shows whether Claude Code and Codex are installed and signed in (**Check again** after signing in), the analysis engine (Claude by default, Codex, or Manual), the generation engine for Phase 5, and each engine's time limit. Each run's files are kept in `jobs\<scene>\analysis-<n>\` (or `polish-<n>\`) inside the private data folder.

## Characters, prompt and approval (Phase 4)

A scene has four steps, shown as tabs above the panels: **Analysis**, **Characters**, **Prompt** and **Review**. A tick marks a finished step. The scene opens on the step its saved stage suggests and stays there until you switch; refreshing keeps the step (`#/scenes/<id>/characters`).

**Characters.** Each person found in the Base Image is a subject (Subject 1, Subject 2, …). For each one choose **Use a character**, **Keep original** or **Decide later**, then **Save assignments**. Click a box on the image to jump to its subject. **Choose from** narrows the list to one of your groups; a group never decides who stands where. Each character can appear only once per scene, and characters without reference photos cannot be chosen. Archived characters are hidden unless already assigned.

**Reference photos.** By default the studio picks up to 3: the primary photo, then the view closest to that subject's face angle, then other distinct views. Click photos to choose them yourself (up to 4, in the order clicked), or **Let the studio choose**. The order decides the attached image numbers (Image 1 is always the Base Image).

**Adjust subjects** lets you click a box to select it, drag it to move it, drag any of its eight side or corner handles to make it larger or smaller (or use the arrow keys; Shift + arrows resize), add a missed person or remove a wrong one. Saving creates a new analysis version. Labels never renumber, so an assignment stays with the same person. If a fresh analysis arrives instead, the studio asks you to check and save the assignments again, because a new analysis may number people differently.

**Prompt.** The template now names each subject's identity images ("Subject 1: take this person's identity only from Image 2 and Image 3") and keeps "Keep original" subjects unchanged. Character names never go into the prompt. If you change assignments after saving a prompt, the studio offers **Rebuild with the assignments**. **Version history** lists every saved version with a preview: **Load into editor** brings one back (save it to make it current) and **Delete version** removes it. The approved version cannot be deleted until you withdraw the approval; approval records keep their own copy of the prompt either way.

**Polish prompt** (optional) asks Claude, through your own Claude Code sign-in, to rewrite the *saved* prompt more clearly under fixed rules: keep every fact, add nothing, keep the subject labels, image numbers and identity instructions. It sends the prompt text and the analysis, never photos. When it finishes, **Compare** shows both versions with removed and added words marked. Choose **Use polished**, **Keep original**, or **Edit by hand**. The studio checks that every subject is still linked to its image numbers with the instruction that its identity comes *only* from them, and that every keep-original instruction is still there; if anything is missing it warns you and you must tick "Use it anyway" to accept. Both versions are kept. Failures leave the prompt unchanged and offer **Try again** or **Edit by hand**; nothing is retried automatically.

**Review and approve.** The Review step shows the Base Image and analysis version, every subject with its character and reference photos (with image numbers), the full prompt and negative prompt, the generation engine and cost notes. **Before you can approve** lists what is missing (for example an undecided subject or unconfirmed analysis details). **Please check** lists warnings (for example a prompt built before the current assignments); tick the box to approve anyway. **Approve scene** saves an unchangeable snapshot of the exact inputs, including content hashes of the Base Image and reference photos.

An approval stays valid across restarts while nothing changes. Changing the analysis, subjects, assignments, reference photos or prompt (including using a polished version), or deleting a photo or character used in the scene, cancels it and shows why. Renaming a character does not. **Withdraw** cancels it yourself. The approval covers the content, not the engine, so changing the generation engine in Settings keeps it. Approval history keeps every snapshot. Generation itself arrives in Phase 5 and will require a valid approval.
