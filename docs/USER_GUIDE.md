# Character Studio — User Guide

A local-first home for reusable characters, reference scenes and approved image workflows. For the project overview, see the [README](../README.md). Commands below run from the project root folder.

**Current scope: Phase 6B quality checks, presets and comparison**, on top of Phase 6A API engines (optional analysis with your own Google, Anthropic or OpenAI API key), Phase 5.5 Batch Processing, Phase 5 Generation and Results, Phase 4 Character Mapping and Approval, Phase 3 Scene Analysis and the Phase 2 Character Library. Add scenes, analyse them, assign saved characters to the people in them, choose reference photos, edit or polish the prompt, approve the exact inputs, then generate with Codex or export the package for any app and import the result. Several scenes can be added, analysed and generated as one batch. Do not upload personal photographs into the source folder.

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

Scene analysis, prompt polishing and image generation run through the official CLIs (Phases 3–5) by default, with no automatic retry. Since Phase 6A, scene analysis can optionally use an **API engine** with your own key (see *API engines* below). Those runs are billed by that company, separately from your plans, and the studio asks before every run or batch. API image generation follows in Phase 6C.

How it works (DECISIONS.md D009): the studio runs `claude -p` (default) or `codex exec` for scene analysis, `claude -p` for optional prompt polishing, and `codex exec` for image generation, each started by your click, with a timeout, cancel and no automatic retry. The manual bridge (export an approved package to Codex/ChatGPT and import the result) is the fallback. The Phase 2.5 spike verified both CLIs' flags, output locations and failure modes; the studio uses only those flags.

Each run uses your plan's allowance and sends data to that provider: **Analyse** sends the Base Image to Anthropic (or to OpenAI if Codex is the analysis engine); **Polish prompt** sends prompt and analysis text to Anthropic; **Generate** sends the Base Image and chosen reference photos to OpenAI. There is no promise of unlimited generation or perfect likeness/pose preservation. See `docs/PROVIDER_FINDINGS.md`.

## Continuity and recovery

- Open a new Codex conversation **in this project folder** and say **Resume Character Studio**.
- Read AGENTS.md, PLAN.md, PROJECT_STATUS.md and SESSION_HANDOFF.md; compare them with actual Git/files before continuing.
- Say **Checkpoint Character Studio** before a planned pause. See `docs/CONTINUITY.md` for the exact protocol.
- Approval covers Phases 1, 2, 2.5, 3, 4, 5 and 5.5. Phase 6 requires explicit approval.

For data recovery see **Backups and restore** below and `docs/RECOVERY.md`. Git backs up source history, not private application data.

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

If copies of those photos were sent to Codex or exported for manual use, they are also saved inside those packages in the scenes' run folders. Before deleting, the studio then asks: **Delete and remove copies** deletes those copies as well (each package keeps its other files, export zips are rebuilt without them, and a deleted character's name is replaced in `mapping.txt`), **Delete, keep copies** leaves them until you delete the scene, or **Cancel**. Nothing is removed without that choice. Results and approval records are kept either way, and packages you already downloaded are not changed. A package with removed photos says so in its README and in the scene's **Manual packages** list.

Save profile edits before changing photos. If a batch upload stops, earlier successful uploads remain saved; reload to verify saved state before selecting remaining files. A stale revision or expired session is rejected. Reload after a service restart. Locked file deletions remain queued and are retried at startup; the UI reports pending cleanup.

## Scenes and analysis

Open **Scenes** and choose **+ New scene**. Pick a JPEG, PNG or WebP Base Image (the scene whose pose, framing and light you want to recreate) and optionally a title. The image stays on this computer until you choose to analyse it. Scenes can be renamed, duplicated (the copy takes the current analysis and prompt) or permanently deleted, either inside the scene or from the **⋯** menu on its card. **Select** lets you tick several scenes and delete them together (scenes with a running analysis are skipped). The Overview lists recent scenes and offers **Resume**.

**Analyse with Claude** (or Codex, if selected in Studio settings) sends the Base Image to that company using your own sign-in and plan allowance. It runs once per click with a progress timer and a **Cancel** button; you may leave the page while it runs. Errors (not installed, signed out, usage limit, time limit, unexpected reply) offer **Try again** and **Do it manually**. Nothing is retried automatically. If the studio stopped mid-run, the run shows as **Interrupted**: check the job folder shown before trying again.

**Do it manually** works with any chat app: copy the instruction, attach the Base Image, paste the whole reply back. It is checked against the same format as engine results.

Analyses are saved as versions with their source and CLI version. Details the analysis was unsure about appear under "Please check": **Confirm** keeps them as written; **Correct** opens the editor. Every edit is saved as a new version; earlier versions can be viewed and restored. When the Base Image shows people, "Show subjects" draws their approximate boxes.

The **Generation prompt** is written by the studio from the analysis (numbered images, "Subject N" labels, identity and composition locks, negative prompt). Edit it freely, add **Scene changes** and rebuild, copy it, and **Save prompt version**. Saved versions can be loaded back into the editor. If the analysis changes, the studio offers to rebuild the prompt.

**Studio settings → Analysis and generation engines** shows whether Claude Code and Codex are installed and signed in (**Check again** after signing in), the analysis engine (Claude by default, Codex, or Manual), the generation engine (Codex by default, or Manual), and each engine's time limit. Each run's files are kept in `jobs\<scene>\analysis-<n>\` (or `polish-<n>\`, `generation-<n>\`, `export-<n>\`) inside the private data folder.

## Characters, prompt and approval (Phase 4)

A scene has five steps, shown as tabs above the panels: **Analysis**, **Characters**, **Prompt**, **Review** and **Generate**. A tick marks a finished step. The scene opens on the step its saved stage suggests and stays there until you switch; refreshing keeps the step (`#/scenes/<id>/characters`).

**Characters.** Each person found in the Base Image is a subject (Subject 1, Subject 2, …). For each one choose **Use a character**, **Keep original** or **Decide later**, then **Save assignments**. Click a box on the image to jump to its subject. **Choose from** narrows the list to one of your groups; a group never decides who stands where. Each character can appear only once per scene, and characters without reference photos cannot be chosen. Archived characters are hidden unless already assigned.

**Reference photos.** By default the studio picks up to 3: the primary photo, then the view closest to that subject's face angle, then other distinct views. Click photos to choose them yourself (up to 4, in the order clicked), or **Let the studio choose**. The order decides the attached image numbers (Image 1 is always the Base Image).

**Adjust subjects** lets you click a box to select it, drag it to move it, drag any of its eight side or corner handles to make it larger or smaller (or use the arrow keys; Shift + arrows resize), add a missed person or remove a wrong one. Saving creates a new analysis version. Labels never renumber, so an assignment stays with the same person. If a fresh analysis arrives instead, the studio asks you to check and save the assignments again, because a new analysis may number people differently.

**Prompt.** The template now names each subject's identity images ("Subject 1: take this person's identity only from Image 2 and Image 3") and keeps "Keep original" subjects unchanged. Character names never go into the prompt. If you change assignments after saving a prompt, the studio offers **Rebuild with the assignments**. **Version history** lists every saved version with a preview: **Load into editor** brings one back (save it to make it current) and **Delete version** removes it. The approved version cannot be deleted until you withdraw the approval; approval records keep their own copy of the prompt either way.

**Polish prompt** (optional) asks Claude, through your own Claude Code sign-in, to rewrite the *saved* prompt more clearly under fixed rules: keep every fact, add nothing, keep the subject labels, image numbers and identity instructions. It sends the prompt text and the analysis, never photos. When it finishes, **Compare** shows both versions with removed and added words marked. Choose **Use polished**, **Keep original**, or **Edit by hand**. The studio checks that every subject is still linked to its image numbers with the instruction that its identity comes *only* from them, and that every keep-original instruction is still there; if anything is missing it warns you and you must tick "Use it anyway" to accept. Both versions are kept. Failures leave the prompt unchanged and offer **Try again** or **Edit by hand**; nothing is retried automatically.

**Review and approve.** The Review step shows the Base Image and analysis version, every subject with its character and reference photos (with image numbers), the full prompt and negative prompt, the generation engine and cost notes. **Before you can approve** lists what is missing (for example an undecided subject or unconfirmed analysis details). **Please check** lists warnings (for example a prompt built before the current assignments); tick the box to approve anyway. **Approve scene** saves an unchangeable snapshot of the exact inputs, including content hashes of the Base Image and reference photos.

An approval stays valid across restarts while nothing changes. Changing the analysis, subjects, assignments, reference photos or prompt (including using a polished version), or deleting a photo or character used in the scene, cancels it and shows why. Renaming a character does not. **Withdraw** cancels it yourself. The approval covers the content, not the engine, so changing the generation engine in Settings keeps it. Approval history keeps every snapshot. Generating needs a valid approval.

## Generate and results (Phase 5)

A scene now has a fifth step, **Generate**. It needs a valid approval: without one it explains why (for example "You withdrew this approval") and offers **Go to review**. An approved scene opens on this step.

**Generate image** builds the approved package in a job folder (`jobs\<scene>\generation-<n>\`): the Base Image and the approved reference photos as numbered JPEGs without location or other metadata (`image-1.jpg` is the Base Image), `prompt.txt`, `negative_prompt.txt`, `mapping.txt` (who is who, without names) and `instruction.txt` (exactly what Codex is asked). Everything comes from the approval snapshot, and each file is checked against the hash recorded at approval, so only what you approved is sent. It then runs `codex exec` once, with your own ChatGPT sign-in, and copies the image Codex saves into the studio's results. A run takes about a minute. You can leave the page or press **Cancel**. Each attempt uses your ChatGPT plan's image allowance; nothing is retried automatically.

**Generate again** and **Variation** each ask for confirmation and add a new result; earlier results are never replaced. A variation sends the same approved prompt with one fixed extra line asking for small natural differences in fine details, without changing composition, poses, outfits or identities.

If a run fails (not installed, signed out, usage limit, time limit, or "finished without producing an image"), the notice shows Codex's own words and offers **Try again**, **Export for manual use** and, when the run got far enough to have a Codex folder, **Look for a saved image**. That button looks only in this run's own Codex output folder (`generated_images\<thread id>\`) and keeps any image it finds as a result marked "recovered"; it never sends anything. A run interrupted by a studio restart is shown as **Interrupted** and is never resubmitted; check its folder or use **Look for a saved image** before **I checked — try again**. Cancelling stops the studio's run, but the request may already have reached OpenAI and used allowance.

**Export for manual use** (always available, and the main action when Manual is the generation engine in Studio settings) creates the same package as a downloadable zip with a README, for ChatGPT or any other image app. Its `mapping.txt` includes character names, because you handle it yourself. **Import result** adds an image you made elsewhere (JPEG, PNG or WebP). Choose the package you used, so the result keeps the exact inputs even if you have changed the scene since; you can also link it to the current approval. "Made with" records where it came from, as you describe it. **Manual packages** lists every package with "Waiting for import" or the number of imported results, and buttons to **Download** it, **Import result**, **Copy folder path** or **Delete** it. Deleting a package removes its folder (the photo copies, prompt files and zip) after a confirmation; results you imported from it are kept and stay linked to their approval, and packages you already downloaded are not affected.

**Results** lists every result of the scene, newest first, with its source (Codex, Codex variation, recovered, or Imported), how long Codex took to make it, and "Earlier approval" when the inputs have changed since. The Generate box also shows the average time per image of your finished Codex runs (even while Manual is the generation engine), a guide for planning batches later; imported and recovered results have no time because the studio did not measure them. Open a result to see it alone, **Side by side** with the Base Image, or with a **Slider** that reveals one over the other. The viewer lists the prompt and analysis versions and the character assignments it was made from, and offers **Mark as preferred**, **Download** and **Delete**. Each result card also has a **⋯** menu with the same three actions, and **Select** lets you tick several results to download (one image, or several as one zip), mark or unmark as preferred, or delete together. A scene can have any number of preferred results. The **Results** page in the sidebar shows every result from every scene, with search, "Preferred only" and the same Select mode, and the Overview shows the latest results.

Deleting a scene deletes its results and run folders. Deleting a character or photo keeps existing results and approval records.

## Batches (Phase 5.5)

**Several scenes at once.** In **+ New scene**, choose several images (up to 30): each becomes its own scene, titled from its file name (you can edit the titles first). The new scenes stay selected, ready for **Analyse**.

**Analyse selected.** On the Scenes page, **Select** scenes and choose **Analyse**. A dialog shows how many runs it makes and which plan allowance it uses, and which scenes are skipped (already analysed, unless you tick the option, or with a run in progress). Runs go one after another with the analysis engine chosen in Studio settings, at most 50 per batch. Each analysis is reviewed on its own scene, with uncertain details flagged as usual.

**Suggest from group.** Select analysed scenes and choose **Suggest from group**: pick a group and arrange its members from left to right. Each scene gets those characters as *suggestions*, matched to its people from left to right; scenes without an analysis, approved scenes and (unless you tick the option) scenes that already have assignments are skipped. Nothing is sent anywhere. A scene with suggestions cannot be approved until you open its Characters step, check who is where and click **Confirm assignments**.

**Generate approved scenes.** Each scene still needs its own approval. Choose **Generate approved scenes** (or Select scenes, then **Generate**): tick the scenes, choose **Images per scene** (1–5) and **New image** or **Variation**. The dialog shows the total ("8 images from your ChatGPT plan's allowance") and an estimate from earlier runs on this computer. A batch makes at most 20 images, because image generation uses the allowance quickly. Each run uses that scene's own approval and is checked again just before it starts. On a scene's Generate step, the **− / +** control makes up to 10 images from that one approval in one click.

**While a batch runs.** The Scenes page (and the Overview) shows each batch with a progress bar, done / failed / not started counts and every item. Waiting scenes show **Waiting to analyse** or **Waiting to generate** and cannot be edited; open one and click **Remove from batch** to take it out. **Pause** lets the run in progress finish and starts nothing new; **Continue** starts the rest; **Cancel remaining** cancels everything that has not started (cancel a running item with **Cancel run**). A failed item is marked Failed and the next one starts. If the plan limit is reached, or the engine is signed out or missing, the batch pauses with the reason; when signed out, the item that found it waits again because nothing was sent. **Continue** checks the sign-in first. If the studio stops during a batch, the running item becomes Interrupted and the batch is paused: nothing continues until you click Continue. When a batch has finished, **Try failed again** runs its failed items once more as new items, and **Remove from list** hides it (its runs and results are kept). Nothing in a batch is ever retried on its own.

## API engines (Phase 6A)

**Optional.** Studio settings → **Analysis engine** → under *Pay per use* choose the **Gemini API** (Google AI Studio → Get API key), the **Anthropic API** (console.anthropic.com) or the **OpenAI API** (platform.openai.com). Its settings open below: paste the key and click **Save key**. Keys are stored only on this computer in `keys\` inside the data folder, encrypted for your Windows account. They are never shown again, never included in backups (a restore keeps them) and only sent to their own company. Saving a key also asks the company which models it can use (free) and keeps that list; **Test key** checks the key again and refreshes the list. Nothing is generated.

**Choose the model.** Open **Model** and pick from the list (search it, or type a name); `gemini-2.5-flash` is marked Recommended (Google's free tier, October 2026). Then **Save analysis engine**. An API engine cannot be saved without a key and a model. **Time limit** is how long the studio waits for an answer.

**Claude Code and Codex models.** Choosing *Claude Code* or *Codex* under *Your subscriptions* shows its sign-in status, **Model** and **Time limit**. *Default* uses your plan's standard model; Claude also offers Opus, Sonnet and Fable (always the latest of each), Codex takes a model name you type. The Claude model is also used for Polish prompt and quality checks. The **Generation engine** panel (Codex or Manual) has its own Save; Codex always uses its built-in image model.

**Costs.** API use is billed by Google, Anthropic or OpenAI, separately from Claude Pro and ChatGPT plans. A Gemini key on the free tier is not charged for analysis with free models, but Google may use free-tier content to improve its products. Every **Analyse**, analysis batch, **Continue** and **Try failed again** with an API engine first shows what is sent, to whom, with which model, how many runs and the typical tokens of earlier runs, and runs only after **…accept charges**. After each run the scene's *Engine runs* list shows the model and the tokens the company reported. Cancelling, or reaching the time limit, stops the studio waiting. A request the company already received may still finish there and be charged. Nothing is retried on its own. A refused key, an unavailable model or a rate, quota or spending limit pauses a batch until you continue it.

**What is sent.** A copy of the Base Image without location data, at most 1568 px on its long side, plus the analysis instruction. Character names are never sent. Each run's folder keeps `request.json` (what was sent, without the key or the image data) and the company's `response.json`.

## Quality checks, comparison and presets (Phase 6B)

**Compare.** Open a result: choose **Result**, **Side by side**, **Slider**, **Overlay** (a slider sets how see-through the result is) or **Difference** (matching areas turn dark, differences light up), and **Compare with** the Base Image or another result of the scene. **−** / **+** zoom up to 4× on every image at once; drag an image (or use the arrow keys) to move around, **Fit** goes back. **Subject boxes** draws the analysis boxes on top. On a scene's Generate step or the Results page, **Select** 2–4 results of one scene and click **Compare** to see them all next to the Base Image. Comparing sends nothing anywhere.

**Quality check.** In the result viewer, **Check quality** asks the analysis engine chosen in Studio settings how closely the result keeps the Base Image's composition (camera and framing, positions, poses, head and gaze, outfits, environment, lighting) and each person's identity, scored from *Does not match* to *Very close*, with short notes, a summary and things worth fixing. It sends the Base Image, the approved reference photos and the result (without location data, without names) and uses your plan's allowance once; with an API engine it first asks you to confirm the possible charge. The card then shows the weaker of the two scores. It is a model's opinion, not a measurement, so look at the images yourself. **Check again** keeps the earlier checks (pick them from the list); **Delete this check** removes one. A result cannot be deleted while it is being checked.

**Presets.** Studio settings → **Generation presets** lists 10 built-in presets (Individual, Couple, Family, Friends) that change light, colour and mood, plus your own. Built-ins cannot be changed: **Customise** opens one so you can save your own version. **+ New preset** or **Edit** on your own: a name, who it is for, scene changes, lines to add to the negative prompt, and how many images one click makes; **Save as new preset** keeps the original. On a scene's Prompt step, the bar below the prompt fields has **Apply a preset** (puts its scene changes in place, rebuilds the draft and adds its negative lines, never twice; save and approve as usual) and **Save as preset** (turns the current scene changes into a preset). On the Generate step (and in **Generate approved scenes**) the **Preset** list sets the image count, and each result remembers the preset's name.

## API image engines (Phase 6C-1)

**Optional.** Studio settings → **Generation engine** → under *Pay per use* choose **Gemini image** (your Google AI Studio key, on a project with billing; image models are not on Google's free tier) or **OpenAI Images** (your OpenAI API key; OpenAI asks organisations to verify themselves first). The same key serves analysis and images, so a key saved in either panel shows in both. Pick an **Image model** (`gemini-nano-banana-2.1` and `gpt-image-2.5-sunburst` are marked Recommended, October 2026), an **Image size** (Gemini 1K, 2K or 4K; OpenAI 1K or 2K) and, for OpenAI, a **Quality** (Low to Max; Medium is a good start). The image keeps the Base Image's shape. **Time limit** is shared with the API analysis engines. Then **Save generation engine**. Both stay marked *unverified* until you run them yourself.

**Generate.** The Generate step works as with Codex, but **Generate image**, **Generate again**, **Variation**, several images per click and **Try again** first show what is sent (the Base Image and the approved reference photos without location data, with the approved prompt; never names), to which company, with which model, size and quality, how many runs, and the tokens of earlier runs, and start only after **…accept charges**. **Generate approved scenes** asks once for the whole batch. A paused batch continues only with the engine it was started with, and **Continue** asks again. Results show the engine, model, size and reported tokens. A preset can set its own **Image size** and **Quality** (Studio settings → Generation presets); Codex ignores them.

**If something goes wrong.** A refused key, an unverified OpenAI organisation, an unavailable model or a rate, quota or spending limit is shown in plain words and pauses a batch. A request the company declines (its content rules) or a reply without an image fails with the company's words; nothing is saved and nothing is retried. Cancelling or the time limit stops the studio waiting, but a request the company already received may still be charged. If the studio stopped after the image arrived but before it was stored, **Look for a saved image** keeps it from the run's own folder.

## Region editing and replacing a person (Phase 6C-2)

**Edit area.** Open a result and click **Edit area**. Mark what to change with the **Brush**, **Eraser** or **Rectangle** (Undo and Clear help), or click **Use a person's area** to mark a subject's approved box. Then choose:

- **Fix an area**: describe the change ("remove the sign on the wall").
- **Replace a person**: pick a subject that was replaced with approved photos; its area is marked for you. Only that subject's **approved** reference photos are sent. To use someone else, duplicate the scene and approve it.

**Engines.** **Codex** (your ChatGPT plan, no charge; told where the area is), **OpenAI Images** (uses the marked area as a guide), **Gemini image** (told where the area is), **FLUX.1 Fill** (follows the marked area exactly; fixes only, it takes no reference photos) and **FLUX 3** (works on a box around the area; can replace a person). OpenAI and Gemini use the image model, size and quality from the Generation engine panel. FLUX needs a Black Forest Labs key: Studio settings → *Region editing with FLUX*. Every API edit asks you to confirm the possible charge; Codex asks before using your plan's allowance. FLUX 3 and OpenAI Images are *unverified* until you run them.

**What you get.** Whatever the engine returns, the studio pastes back **only the marked area** (with a soft edge inside it), so every pixel outside it is exactly the original. The edit is a new result ("Edited" or "Replaced Subject 1"); the original is kept. The viewer compares it with the result it came from, says what was asked and links the marked area. If the engine returned a different shape, its image was stretched to fit first, and the viewer says so. Results whose approval you withdrew cannot be edited. A result cannot be deleted while it is being edited.

**If something goes wrong.** Failures and refusals are reported in plain words; nothing is retried. If the studio stopped after the image was made, **Look for a saved image** keeps it: from the run's folder, Codex's own folder, or (FLUX) by asking Black Forest Labs once more about the same task, free and without resending.

## Backups and restore

**Studio settings → Backups → Create backup** saves one file, `backups\character-studio-backup-<date>-<time>.zip`, inside your data folder. It holds the database (copied with SQLite's own backup method), your characters and photos, scenes, results, thumbnails and run folders, plus a manifest with a fingerprint (SHA-256) of every file. While it starts, saving pauses for a moment; the zip itself is written in the background and the studio keeps working. Each backup shows its date, size and what it contains. **Check** re-reads every file against its fingerprint and checks the database; **Download** saves it through your browser; **Delete** removes it from the data folder.

**Password-protected backups (Phase 6D).** **Create backup** asks which kind you want. **Protect with a password** (shown first) encrypts the whole backup (AES-256-GCM, key made from your password with scrypt) into `character-studio-backup-<date>-<time>.csbackup`; type the password twice (at least 10 characters; a few words work well). **Plain backup** makes the usual zip. The password is never saved, logged or shown again: if it is forgotten, nobody can open that backup, not even you, so keep it in a password manager. A protected backup shows a **Password protected** tag; its contents appear after **Check**, which asks for the password and checks every file just like a plain backup. A wrong password, or a file that was changed or damaged, is reported and nothing else happens. **Download** gives you the protected file as it is, ready for a USB drive or cloud storage.

Backups live in the data folder, so a disk failure would take them too: download them or copy them to another drive (protect those copies with a password). Server logs, the launcher's process record and folders the studio does not manage (for example the Phase 2.5 `spike-2.5` test folder) are not included.

**To restore:** double-click **Stop-Studio.cmd**, then **Restore-Studio.cmd**. It refuses while the studio is running. It lists the backups in your data folder (newest first) and restores the one you pick after you type `RESTORE`; to restore a downloaded backup, drop the `.zip` or `.csbackup` file onto Restore-Studio.cmd. For a protected backup it asks for the password (what you type is not shown); a wrong password stops the restore and changes nothing. It first checks and unpacks the whole backup into a new folder; only if everything matches does it rename your current data folder to `Character-Studio-Data.before-restore-<time>` and put the restored one in its place. Nothing is deleted or overwritten, your backups move with you, and a backup made by a newer studio version is refused. Then start the studio. When you are sure the restored data is right, you can delete the `before-restore` folder yourself.
