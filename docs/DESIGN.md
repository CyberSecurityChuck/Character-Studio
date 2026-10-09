# Foundation design direction

Phase 1 uses a quiet, light desktop workspace: warm neutral surfaces, charcoal text, restrained terracotta actions and a simple overview/settings navigation. System fonts avoid remote font requests. Typography, semantic color tokens, visible keyboard focus, real loading/error states and responsive layouts support the image-focused product planned in PLAN.md.

The UI/UX skill's refined search returned a relevant flat web-app style. Its marketing-page layout and animation suggestions did not fit a local studio and were not adopted. The warm palette and serif editorial accent are implementation choices; accessibility is validated on the actual interface. Decorative composition artwork uses CSS, contains no private images and is hidden from assistive technology.

Future features are labeled as later phases, not fake working buttons. Current settings are controlled inputs with explicit saving feedback and conflict protection. No remote assets, paid generation or photos are used by this shell.


## Phase 2 library

The same warm palette and system fonts now support a responsive character gallery and profile editor, with a separate group editor. Search, filters and archive state use labeled native controls. Upload progress, errors, partial-success guidance and saved feedback are visible; unsaved profile/group edits are guarded. A native modal dialog provides keyboard focus containment for original-photo previews. Busy writes disable navigation and related controls.

The UI/UX skill's focused form-error search supported announced/focusable errors; React guidance supported controlled fields and normal form submission. No new visual system or animation dependencies were added. Browser QA covered desktop/mobile widths and original preview, with synthetic photos only.
