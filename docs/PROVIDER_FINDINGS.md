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
