# Foundation design direction

Phase 1 uses a quiet, light desktop workspace: warm neutral surfaces, charcoal text, restrained terracotta actions and a simple overview/settings navigation. System fonts avoid remote font requests. Typography, semantic color tokens, visible keyboard focus, real loading/error states and responsive layouts support the image-focused product planned in PLAN.md.

The UI/UX skill's refined search returned a relevant flat web-app style. Its marketing-page layout and animation suggestions did not fit a local studio and were not adopted. The warm palette and serif editorial accent are implementation choices; accessibility is validated on the actual interface. Decorative composition artwork uses CSS, contains no private images and is hidden from assistive technology.

Future features are labeled as later phases, not fake working buttons. Current settings are controlled inputs with explicit saving feedback and conflict protection. No remote assets, paid generation or photos are used by this shell.


## Phase 2 library

The same warm palette and system fonts now support a responsive character gallery and profile editor, with a separate group editor. Search, filters and archive state use labeled native controls. Upload progress, errors, partial-success guidance and saved feedback are visible; unsaved profile/group edits are guarded. A native modal dialog provides keyboard focus containment for original-photo previews. Busy writes disable navigation and related controls.

The UI/UX skill's focused form-error search supported announced/focusable errors; React guidance supported controlled fields and normal form submission. No new visual system or animation dependencies were added. Browser QA covered desktop/mobile widths and original preview, with synthetic photos only.

## Phase 2 review refinements (2026-10-10)

After the user's hands-on review: round avatars with user-adjustable framing (drag/zoom editor, live previews at card, header and mini sizes); a two-column profile form and compact photo cards; group chips and member avatar stacks; one primary "+ New group" action; a footer action bar for the short group form (Delete left, Cancel and the primary action right) while the long character profile keeps Close at top-right; matching panel heights for the group placeholder; line icons for every sidebar item. Hash routes keep the current view across refresh. Browser QA used isolated synthetic data at desktop and 375px widths.

## Phase 3 scenes and analysis (2026-10-10)

Scenes reuse the warm palette and system fonts: an image-first card grid, a short new-scene dialog with footer actions, and a two-column workspace (sticky Base Image with optional subject boxes; numbered "Scene analysis" and "Generation prompt" steps). Each action appears once per state: while a run notice is shown, the start and version-bar run actions are hidden. Analysis fields use compact labelled grids; unsure details are highlighted and grouped with Confirm/Correct. Progress, failure, cancelled and interrupted states have distinct, plain-language notices. Engine settings use status cards, choice cards for the analysis engine and a footer action bar. Browser QA covered desktop and 375 px widths with synthetic images.

## Phase 3 review refinements (2026-10-11)

Cards on Scenes, Characters and Groups gain a quiet ⋯ menu (top-right; on group rows, vertically centred) and a Select mode with tick boxes and an accent selection bar, so frequent actions no longer require opening an item. Settings explanations live in small ⓘ tooltips rather than permanent helper text. Analysis text is shown in sentence case. Cancel switches to "Stopping…" at once. Side-by-side Groups panels share one height.

## Phase 4 mapping, polish and approval (2026-10-11)

The scene workspace gains a four-step tab bar (Analysis, Characters, Prompt, Review) with numbered pills that turn into green ticks; panels stay mounted so unsaved edits survive tab switches, and a quiet "Next" button closes each finished step. The Base Image stays sticky on the left: boxes are clickable on the Characters step, tags show the assigned character's avatar and name, and Adjust subjects turns them into draggable boxes with a corner handle and a short action bar under the image. Each subject is a card with an accent label chip, a three-way segmented control, avatar tiles for characters (unavailable ones dimmed with a reason) and square reference tiles numbered as attached images. One orange primary action per panel (Save assignments, Save prompt version, Approve scene). The polish comparison is a wide modal with two monospace columns, red strikethrough for removed and green for added words, and a footer with Decide later / Keep original / Use polished. Review uses compact cards, a green approved banner and coloured check boxes (blocked, please check, all clear). Browser QA covered 1440 px and 375 px widths with synthetic images and the fake CLI.

## Phase 4 review refinements (2026-10-11)

Subject box labels show the avatar beside the text again. The selected box in Adjust subjects carries eight white, accent-bordered handles (corners and side midpoints) with enlarged invisible grab areas and matching resize cursors. Prompt versions move from a dropdown into a Version history dialog: a version list with Current and Approved badges on the left, a monospace preview on the right, and a footer with Delete version (left) and Close / Load into editor (right). On phones the list stacks above the preview.

## Phases 5–6 (2026-10-11 to 2026-10-12)

Results open in a viewer with a comparison bar (Result, Side by side, Slider, Overlay, Difference) and shared zoom and pan; "Made from" and "Quality check" sit below as full-width cards. Engine settings use grouped choice cards (Your subscriptions, Pay per use, Without an engine) with Subscription / API key tags and details for the selected engine only; a searchable model picker marks a Recommended model. Every possibly charged run opens a charge dialog that lists what is sent, to whom, the model, size and run count before "…and accept charges". The Edit area dialog pairs a large canvas (brush, eraser, rectangle, a person's area, undo, clear) with a form column (what to do, instruction, engine cards that explain unavailable engines); the marked area is a translucent terracotta overlay. Backups offer a protected or plain backup in one dialog with clear password rules and a warning. Success is confirmed twice for now (review choice D029): a toast in the top-right corner and a green inline banner or "Saved" pill; problems stay in red beside their cause. A disabled control is always explained in visible text, not only a tooltip.
