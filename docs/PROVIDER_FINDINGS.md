# Provider verification — Phase 0, 2026-10-09

These are dated findings, not permanent entitlements. Reverify before implementing any provider.

- This Codex conversation exposed built-in image generation/editing and image viewing. Tool contracts supported reference images. No live generation or image-analysis accuracy test was performed in planning.
- The installed imagegen skill states that built-in image generation does not need an API key and can produce saved image artifacts. It does not establish an application-callable image service.
- Official built-in image documentation describes generation using Codex allowances and reference images. Usage is limited; it is not free unlimited API access.
- Official App Server supports image inputs and thread persistence. Its suitability for this user's authenticated analysis workflow has not been runtime-tested.
- Official Sign in with ChatGPT plan-backed inference documentation includes image inputs but explicitly excludes hosted image generation on that route. Eligibility was not verified.
- OpenAI image/vision APIs are documented alternatives with separate credentials/billing. They are outside current scope and disabled.

Sources checked:

- https://learn.chatgpt.com/docs/image-generation
- https://learn.chatgpt.com/docs/app-server
- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/pricing

## Initial provider boundary

The application only exposes capability/status metadata and typed Python analysis/generation protocols. All execution is unavailable in Phase 1. No calls, retries, browser automation, credential extraction or unofficial endpoints exist.

MVP plan: manual analysis import and approved generation package export/import. The app preserves provenance, versions and approvals. The external UI performs inference after an explicit user request. Saved characters avoid repeated local uploads but selected references still need to accompany external generation requests.

Adapters must later report supported formats, reference limits, editing, masks, resolutions, model/settings, status lookup, idempotency, external transfer and costs. Unknown values stay unknown. Provider capabilities and software workflow correctness do not guarantee visual likeness or composition accuracy.

The Phase 0 MVP plan above is superseded as the main path by D009 (below); manual import/export remains the fallback.

# Subscription-use findings — 2026-10-10 (D009)

Recorded from the user's planning direction on 2026-10-10. Not independently re-checked in that planning session; cite sources and reverify during Phase 2.5 and before implementing each engine.

- The studio may run the **official** `claude` (Claude Code) and `codex` (Codex CLI) programs locally, for the user's personal use, on the subscriptions the user signed into themselves: Claude Pro for analysis and prompt polishing, a ChatGPT plan with image generation (Plus or above) for images.
- Anthropic allows subscription logins only inside Claude Code and Claude.ai. Subscription credentials must not be extracted into other tools, SDK wrappers or third-party gateways (for example OmniRoute).
- Scripted or automated use of the chatgpt.com / claude.ai websites breaks the providers' terms. No browser automation against either site.
- The studio never reads, copies, stores, logs or forwards either CLI's login tokens or credential files. It only launches the programs and reads their output.
- No API keys and no per-use billing. Each run consumes the relevant plan's usage allowance; usage limits can be reached.
- Per the user, OpenAI's documentation confirms Codex built-in image generation with reference photos and identity preservation. Whether likeness is acceptable for this studio's scenes is a quality check recorded by the spike, not a gate.
  Phase 2.5 must cite the exact official OpenAI page; until then this remains the user's statement.
- Codex CLI is also a user-selectable analysis engine (Claude is the default). Codex analysis uses the ChatGPT plan's allowance, which may be shared with image generation (to be confirmed).
- Neither CLI is assumed to confine file reads to its working folder. Phase 2.5 records any supported confinement option; if none exists, that is a known limitation, not a blocker.
- The optional paid OpenAI API adapter remains disabled. Paid API-based engines for analysis and generation are planned post-MVP, off by default, with separate approval and per-run cost confirmation.

## Phase 2.5 spike results

_Completed 2026-10-10. Approved by the user ("Approve Phase 2.5") on 2026-10-10 (Asia/Kolkata). Test files (copies of the user's photos, outputs, logs) are in `%USERPROFILE%\Character-Studio-Data\spike-2.5\`, outside the repository. The generated image also remains under `%USERPROFILE%\.codex\generated_images\`._

**Outcome:** The spike gate is met, because all mechanics are confirmed (flags, output location, failure appearance). Both analysis engines work and stay inside their job folders. Codex generation works from the CLI with attached reference photos, and the user judged the likeness "clearly me". The official OpenAI documentation still does not promise identity preservation (see row d).

**Implementation notes for Phases 3 and 5:**
- Launch each CLI as a child process in its job folder with stdin closed (`< /dev/null` equivalent). Remove inherited `CLAUDE*`/`ANTHROPIC*` variables so no host app's connection or credentials leak into the run, and never pass any credential.
- Before each run, check sign-in with `claude auth status` or `codex login status`. Codex otherwise takes about 18 s of retries before reporting a 401.
- Claude: read `is_error`, `result` and `structured_output` from `--output-format json`. Ignore `total_cost_usd`, which is an API-equivalent estimate and not a charge.
- Codex: use `--json` events plus `-o` for the final message. Analysis runs use `-s read-only --disable image_generation`. Generation runs use `-s read-only` with image generation on; references are attached with `-i`, and `--` goes before the prompt.
- Decide a generation's success only by a returned image path inside `generated_images\<thread_id>\` that exists and decodes. Exit code 0 can still mean "no image".
- Enforce timeouts externally; killing the process left no stray processes in these tests.
- Not observed and handled generically: usage/plan-limit messages and schema failures.

| Item | Result |
| --- | --- |
| Date run | 2026-10-10 (in progress) |
| `claude` version / signed in | 2.1.296 (Claude Code). `claude auth status`: **not signed in** (`loggedIn: false`). The Claude desktop app has its own login; the standalone CLI needs its own sign-in by the user. |
| `codex` version / signed in | codex-cli 0.162.1. `codex login status`: "Logged in using ChatGPT". `codex features list`: `image_generation` stable, enabled; `view_image` stable, enabled. |
| Confirmed `claude -p` flags (from `claude --help`) | `-p/--print`; `--output-format text/json/stream-json`; `--json-schema <schema>` (structured output validation); `--tools <tools...>` (restrict built-in tools, e.g. `Read`; `""` disables all); `--allowedTools` / `--disallowedTools`; `--permission-mode` (incl. `dontAsk`); `--permission-prompts none`; `--restricted`; `--add-dir`; `--no-session-persistence`; `--model`; `--system-prompt` / `--append-system-prompt`; `--strict-mcp-config` / `--mcp-config`; `--setting-sources`; `--safe-mode`. **Not usable here:** `--bare` (accepts only `ANTHROPIC_API_KEY`/apiKeyHelper, never the subscription login); `--max-budget-usd` (API billing only). |
| Confirmed `codex exec` flags (from `codex exec --help`) | `[PROMPT]` or stdin (`-`); `-i/--image <FILE>...` (attach images); `-s/--sandbox read-only/workspace-write/danger-full-access`; `-C/--cd <DIR>`; `--skip-git-repo-check`; `--ephemeral`; `--output-schema <FILE>`; `-o/--output-last-message <FILE>`; `--json` (JSONL events); `-m/--model`; `--enable/--disable <FEATURE>`; `--ignore-user-config`; `--add-dir`. Status commands: `codex login status`, `codex features list`. |
| (b) Claude analysis: JSON clean? duration | **Pass.** One-person garden scene (user-supplied, likely AI-generated). Command, run in the job folder with `CLAUDE*`/`ANTHROPIC*` environment variables removed (this chat's desktop-app variables must not leak into the CLI; the studio must launch it with a clean environment): `claude -p "<instruction>" --tools Read --restricted --strict-mcp-config --output-format json --json-schema "<schema JSON>" --no-session-persistence --permission-prompts none < /dev/null`. Exit 0, 49 s wall (42 s API), 3 turns, model `claude-opus-5-5` on the Pro login. The JSON envelope has `is_error`, `subtype`, `result` and a schema-validated `structured_output` object, so no text parsing is needed. Quality: detailed camera/pose/outfit/lighting; eyes behind sunglasses correctly listed in `uncertainties`; it also flagged a corner watermark not to recreate. The envelope's `total_cost_usd` (0.118) is an API-equivalent estimate; with a subscription login it is not billed, and the studio must not show it as a charge. Without `< /dev/null` the CLI waits 3 s for stdin and warns. |
| (b) Claude failure appearance: signed out / usage limit / bad JSON | **Signed out** (simulated with an empty temporary `CLAUDE_CONFIG_DIR`; real login untouched): exit 1 after 1 s, `is_error: true`, `terminal_reason: "api_error"`, `result: "Not logged in · Please run /login"`. Also detectable up front with `claude auth status` (`loggedIn`, `authMethod: "claude.ai"`, `subscriptionType: "pro"`). **Timeout:** an external 6 s timeout gave exit 124 and empty output; no `claude` process was left running. **Usage limit:** not observed (cannot be simulated safely); handle any `is_error: true` not otherwise recognised as a generic engine error that shows the CLI's `result` text. **Bad JSON:** not observed; `--json-schema` makes the CLI validate structure itself, and the studio still validates `structured_output` against its own schema. |
| (b2) Codex analysis: JSON clean? duration | **Pass.** Same image, instruction and schema. Command (clean environment, job folder): `codex exec --skip-git-repo-check --ephemeral --ignore-user-config -s read-only --disable image_generation -C <job> -i <job>/base.jpg --output-schema <schema.json> -o <job>/last-message.json --json -- "<instruction>" < /dev/null`. Exit 0, 52 s wall. JSONL events: `thread.started`, `turn.started`, `item.completed` (agent_message), `turn.completed` (with token usage). `-o` wrote the final message as clean JSON matching the schema. Put `--` before the prompt because `-i` accepts several values. Quality is comparable to Claude: same subject box, the same eye-direction and hidden-foot uncertainties, plus camera-height uncertainty. Claude was somewhat more detailed (pose, environment) and was the only one to flag the watermark. stderr prints "Reading additional input from stdin..." even with `< /dev/null` (harmless). |
| (b2) Codex analysis failure appearance | **Signed out** (simulated with an empty temporary `CODEX_HOME`; real login untouched): exit 1 after **18 s**, because it retries 5 times. JSONL `error` events "Reconnecting... n/5 (unexpected status 401 Unauthorized ...)", then `turn.failed` with a 401 message. The studio should check `codex login status` before each run so it can show a fast, clear "signed out" message. **Timeout:** an external 8 s timeout gave exit 124; no `codex` process was left running. **Usage limit:** not observed (cannot be simulated safely). |
| File-access confinement option: `claude` / `codex` | **claude: confirmed.** `--restricted` confines file tools to the working directories (plus `--add-dir`), removes command-running tools and WebFetch, and ignores user/project/local settings. Test: asked to read `../../analysis-instruction.txt` from a job folder, it replied "BLOCKED" and `permission_denials` recorded the refused Read; reading `base.jpg` inside the folder worked. **codex (analysis setup): effectively confined.** With `-s read-only --ignore-user-config` in `codex exec`, an explicit request to run a shell command reading a file outside the job folder failed with "exec_command failed: blocked by policy". In this mode Codex sees only the attached `-i` images and the prompt. (A first, softer probe was inconclusive because Codex answered without trying.) Generation setup to be checked in test (c). |
| (c) Codex generation: output file location, duration | **Pass (mechanics).** Inputs: the same garden scene (Image 1) plus 2 photos of the user, who consented (Images 2–3). Prompt from the planned template (numbered images, identity lock, composition lock, do-not list). Command (clean environment, job folder): `codex exec --skip-git-repo-check --ephemeral --ignore-user-config -s read-only -C <job> -i <job>/base.jpg -i <job>/ref-1.jpg -i <job>/ref-2.jpg -o <job>/last-message.txt --json -- "<prompt>" < /dev/null` (image generation left enabled; no shell commands were needed). Exit 0, **72 s** wall. Output: one PNG, 867×1815 (same ~1:2.1 aspect as the 383×801 base), saved at `%USERPROFILE%\.codex\generated_images\<thread_id>\exec-<uuid>.png`, where `<thread_id>` equals the `thread.started` event's `thread_id`. The final message (`-o`) contained the full path. This works with `--ephemeral` and `-s read-only`. The studio should take the path from the final message, check it is under `generated_images\<thread_id>\`, and copy it into results; it should not scan the folder. Composition fidelity (observed): bench, blossom tree, hedges, foreground blur, outfit, sunglasses, watch, framing and lighting closely match; the leg cross is similar but not identical; the expression shows a slight smile where the base was neutral; the watermark was not reproduced. Usage: 83k input tokens (63k cached), 719 output tokens. |
| (c) Codex failure appearance | **No image produced** (simulated with `--disable image_generation`; no allowance used for images): **exit 0** after 17 s; the final message only says built-in image generation isn't available, and no file is created. Success must therefore be decided by a valid image path under `generated_images\<thread_id>\` that exists and decodes, never by the exit code. **Signed out / timeout:** same behaviour as (b2). **Plan image limit:** not observed (cannot be simulated safely); treat a missing image together with an error or limit message in the final message or JSONL `error`/`turn.failed` events as a failed attempt, show the CLI text, and never retry automatically. |
| (c) Likeness verdict (user) | **"Yes, clearly me"** (user, 2026-10-10), on one test with one subject and two reference photos. Multi-person scenes and other lighting or poses are not yet tested. |
| (d) Official OpenAI page cited for reference-photo identity support | **Not confirmed.** The official page https://learn.chatgpt.com/docs/image-generation (read 2026-10-10) supports attaching reference images (`-i/--image`) to transform or extend an existing image, and asks users to confirm permission to use a real person's likeness. It does **not** state that identity/likeness is preserved. It states built-in generation uses `gpt-image-2`, counts toward general Codex usage limits and uses them 3–5x faster on average. Save location and `codex exec` support are not stated. No other official page found. Likeness therefore rests on test (c). |
| Notes / sources cited | Unofficial community READMEs (not relied on; to verify in test (c)) report: output under `~/.codex/generated_images/<session-id>/`; up to 5 reference images; `-i` may not reliably expose files outside the working directory, so copy references into the job folder with simple names; put `--` before the prompt because `-i` takes several values. Tools in those results that call Codex image endpoints directly are unofficial endpoints and remain prohibited by D009. |

## Phase 3 implementation notes (2026-10-10)

- Analysis runs use exactly the spike commands above, from the job folder, with stdin closed.
- Removed from the child environment: `CLAUDE*`, `ANTHROPIC*`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CODEX_API_KEY` (subscription login and official endpoint only).
- Windows: `claude` resolves to a native `claude.exe` and runs directly. `codex` resolves to the npm `codex.cmd` shim; the studio runs the package's `node_modules\@openai\codex\bin\codex.js` with node instead, so the prompt never passes through cmd.exe (D012).
- Status: `claude auth status` (only `loggedIn` and `subscriptionType` are read) and `codex login status` ("Logged in" text). Nothing else from these outputs is kept.
- Usage-limit wording is still unobserved; it is matched heuristically and otherwise reported as a generic engine error with the CLI's own text.
- Not yet run through the studio against the real CLIs; the first real run is the user's during Phase 3 review.

## Phase 4 implementation notes (2026-10-11)

- Polish prompt runs `claude -p "<instruction>" --tools "" --restricted --strict-mcp-config --output-format json --json-schema '{"prompt": string}' --no-session-persistence --permission-prompts none` from its own job folder with stdin closed and the same cleaned environment. `--tools ""` (no tools at all) is the documented form from `claude --help` recorded in Phase 2.5; it has not yet been run against the real CLI by the assistant (the first real polish is the user's, during review).
- The instruction (fixed rules, the saved prompt, the analysis as compact JSON) is one command-line argument, so the studio refuses polishing above about 24,000 characters (Windows allows about 32,000).
- The result is read from `structured_output.prompt`, falling back to `result`. Errors use the same signed-out / usage-limit / time-limit handling as analysis. The candidate is stored with the job and only becomes a prompt version when the user accepts it.
- Nothing is sent to OpenAI in Phase 4. Reference photos are selected and approved but not sent anywhere until Phase 5.

## Phase 5 implementation notes (2026-10-11)

- Generate runs, from the job folder with stdin closed and the cleaned environment: `codex exec --skip-git-repo-check --ephemeral --ignore-user-config -s read-only -C <job> -i <job>/image-1.jpg -i <job>/image-2.jpg … -o <job>/last-message.txt --json -- "<instruction>"`. Image generation is left enabled; this is the Phase 2.5 (c) command with the files renamed to match the prompt's image numbers.
- The instruction wraps the approved prompt and negative prompt with fixed text (D016) and asks Codex to reply with only the saved file's full path. It is one argument, so the studio refuses runs above 24,000 characters.
- Success: the final message must name an image under `<CODEX_HOME or %USERPROFILE%\.codex>\generated_images\<thread_id>\` (thread id from the `thread.started` event) that exists and decodes. Exit codes are ignored. The studio copies it into its own results folder and leaves Codex's copy in place.
- Failures: `error` / `turn.failed` events and the final message are classified as signed out, usage limit or a generic error with Codex's own text; a run that ends without a reported image is "no image". Usage-limit wording for image generation is still unobserved and matched heuristically.
- Recovery reads only one run's `generated_images\<thread_id>\` folder and only when the user clicks "Look for a saved image". The studio never reads Codex's login files.
- Not yet run through the studio against the real Codex CLI by the assistant (each run uses the user's image allowance); the first real Generate is the user's, during the Phase 5 review. Multi-person likeness is untested.

## Google Gemini API (desk research for Phase 6, 2026-10-11; nothing built or called)

Sources: https://ai.google.dev/gemini-api/docs/pricing and https://ai.google.dev/gemini-api/docs/image-generation (read 2026-10-11). Re-verify before building.

- Free tier: text and vision models (for example the 2.5 and 3.x Flash and Flash-Lite families, 2.5 Pro) are "Free of charge", so a free AI Studio key can test scene analysis. All image-output models are "Not available" on the free tier, so generation needs billing.
- Image models: Nano Banana 2.1, Nano Banana 2 (`gemini-3.1-flash-image`), Nano Banana 2 Lite, Nano Banana Pro (`gemini-3-pro-image`); `gemini-2.5-flash-image` is deprecated and shuts down on 2026-10-02. Model names change often, so do not hard-code them.
- Editing: text-instructed and conversational edits of a supplied image; up to 14 reference images in total, of which up to 4 (Flash) or 5 (Pro) can be "character" images for consistency; Lite takes no character images. No mask or inpainting is documented. Likeness preservation is not quantified.
- Every generated image carries a SynthID watermark. The user must have the rights to the images uploaded.

## Phase 6 start: re-checked facts (2026-10-11; nothing real was called)

Sources read 2026-10-11: https://ai.google.dev/gemini-api/docs/pricing (page "Last updated 2026-10-09"), https://developers.openai.com/api/docs/guides/image-generation, https://developers.openai.com/api/docs/pricing, https://docs.bfl.ai/ and BFL's FLUX.1 Fill [pro] API reference. Stability AI's developer pages did not render for the fetcher, so its prices and editing features are **unverified** and it is not built.

- Gemini: the free tier still lists text/vision models (3.8/3.6 Flash, 3 Flash Preview, 3.5/3.1 Flash-Lite, 2.5 Pro/Flash/Flash-Lite, Gemma 4) as free. Every image-output model is "Not available" on the free tier. Paid per-image (Standard): Nano Banana 2.1 about $0.034 (1K); Nano Banana 2 (`gemini-3.1-flash-image`) $0.067 (1K); Nano Banana 2 Lite $0.034; Nano Banana Pro (`gemini-3-pro-image`) $0.134 (1K/2K). `gemini-2.5-flash-image` shut down on 2026-10-02.
- OpenAI Images: models listed as `gpt-image-2.5-sunburst` (editing precision) and `gpt-image-2.5-flare` (fast). The edits endpoint accepts several images (examples use four) and a mask on the first image; masking is prompt-based and "may not follow the mask's exact shape". Quality low…max, sizes up to a 3840 px edge (above 2560×1440 experimental). Pricing is per token; use OpenAI's calculator.
- Black Forest Labs: FLUX 3 is the headline family; FLUX.2 and FLUX.1 Kontext remain. FLUX.1 Fill [pro] (`POST https://api.bfl.ai/v1/flux-pro-1.0-fill`, header `x-key`) inpaints with a black/white mask or an alpha channel. Results are polled. No free credits are mentioned.
- Model names change often; the studio stores the user's chosen model and suggests only `gemini-2.5-flash`.

## Phase 6A implementation notes (2026-10-11)

- Endpoints: Gemini `POST /v1beta/models/{model}:generateContent` (`x-goog-api-key`), list `GET /v1beta/models` (filtered to `generateContent`). Anthropic `POST /v1/messages` (`x-api-key`, `anthropic-version: 2023-06-01`) with a forced `save_scene_analysis` tool, list `GET /v1/models`. OpenAI `POST /v1/chat/completions` (`Authorization: Bearer`) with `response_format: json_object`, list `GET /v1/models` (filtered to likely chat models).
- Usage recorded: Gemini `promptTokenCount` and `candidatesTokenCount + thoughtsTokenCount`; Anthropic `input_tokens`/`output_tokens`; OpenAI `prompt_tokens`/`completion_tokens`.
- Error mapping and blocked/cut-off replies are described in DECISIONS.md D022. Gemini reports an invalid key as HTTP 400 "API key not valid", which is matched by text.
- All of this is tested only against a local fake server. The first real run is the user's, during the Phase 6A review; until then the engines are `unverified` in the provider registry.

## Phase 6 review: CLI model flags (2026-10-12)

Read from the installed CLIs' help (no runs): `claude --help` — `--model <model>`: "an alias for the latest model (e.g. 'fable', 'opus', or 'sonnet') or a model's full name". `codex exec --help` — `-m, --model <MODEL>`: "Model the agent should use". `codex` has no model-list command. The studio passes the flag only when the user chose a model; for Codex generation it is not offered, because built-in image generation uses its own image model (`gpt-image-2`, Phase 2.5 row d). Real runs with a chosen model are the user's.
