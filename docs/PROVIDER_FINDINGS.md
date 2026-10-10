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
- The optional paid OpenAI API adapter remains disabled.

## Phase 2.5 spike results

_Not run yet. Requires explicit "Approve Phase 2.5"._

| Item | Result |
| --- | --- |
| Date run | — |
| `claude` version / signed in | — |
| `codex` version / signed in | — |
| Confirmed `claude -p` flags (from `claude --help`) | — |
| Confirmed `codex exec` flags (from `codex exec --help`) | — |
| (b) Claude analysis: JSON clean? duration | — |
| (b) Claude failure appearance: signed out / usage limit / bad JSON | — |
| (c) Codex generation: output file location, duration | — |
| (c) Codex failure appearance | — |
| (c) Likeness verdict (user) | — |
| Notes / sources cited | — |
