# CHARACTER STUDIO
## Master Architecture, Implementation & Continuity Plan

**Version:** 2.1
**Revision 2.1 (2026-10-10):** CLI bridge first, manual bridge as
fallback (DECISIONS.md D009). Adds Phase 2.5 and updates
§8.3, §12, §20, §22 and Phases 3–5.
**Project Status:** Planning
**Implementation Status:** Not Started
**Development Environment:** Codex
**Application Type:** Local-First AI Image Generation Studio

---

# 1. PROJECT VISION

Character Studio is a local-first AI image creation application
designed to recreate scenes from reference images while replacing
the original subjects with selected characters from a persistent
Character Library.

The user will upload a Base Image, the application will analyze
its scene and composition, and the user will select previously
saved characters whose identities should appear in the image.

The application will then prepare a detailed generation prompt,
allow the user to review and approve it, and generate an image
using an available image-generation provider.

The system must support:

- Women
- Men
- Children
- Couples
- Families
- Groups containing multiple people
- Repeated use of characters across different scenes

The user must not need to upload the same character photographs
every time.

## Primary Goals

1. Build a reusable Character Library.
2. Accurately analyze Base Images.
3. Generate detailed scene-recreation prompts.
4. Assign saved characters to subjects in scenes.
5. Preserve scene composition while replacing identities.
6. Require user approval before image generation.
7. Support multiple image-generation providers.
8. Save scenes, prompts, mappings, and generation history.
9. Provide reliable pause/resume functionality.
10. Make the entire workflow simple and accessible.

## Fundamental Principle

Character Reference = WHO appears.

Base Image = HOW and WHERE they appear.

The application must enforce this distinction throughout
the generation pipeline.

---

# 2. REFERENCE PRIORITY RULES

## 2.1 Base Image — Composition Authority

The Base Image determines:

- Camera position, height, and viewing angle
- Camera perspective and framing
- Subject placement
- Body posture and pose
- Torso and shoulder orientation
- Head tilt and rotation
- Facial viewing angle
- Eye and gaze direction
- Facial expression
- Hand, arm, leg, and foot positioning
- Outfit and garment details
- Hairstyle and accessories
- Environment and background
- Lighting and shadows
- Colors and visual atmosphere
- Overall visual style
- Image crop and aspect ratio

The system must describe these elements as accurately
as the Base Image allows.

## 2.2 Character Reference — Identity Authority

Character photographs determine:

- Recognizable facial identity
- Facial structure and proportions
- Distinctive facial characteristics
- Natural skin tone
- Stable visual identity characteristics

Character photographs must NOT determine:

- Camera angle
- Pose or posture
- Head rotation
- Expression
- Gaze
- Outfit
- Scene lighting
- Background
- Image framing

Unless the user explicitly requests otherwise.

## 2.3 Conflict Resolution

When the references conflict:

1. Use the Character Reference for identity.
2. Use the Base Image for composition and appearance.
3. Follow explicit user-requested modifications.
4. Avoid inventing details when information is uncertain.

These rules must appear in the generation prompt.

---

# 3. TECHNOLOGY ARCHITECTURE

Build a local web application that runs on the user's
computer and opens in a browser.

## Frontend

- React
- TypeScript
- Vite
- Responsive, image-focused interface

## Backend

- Python
- FastAPI
- Pydantic
- Background job handling where necessary

## Database

- SQLite
- Versioned database migrations
- Transaction-safe persistence

## Image Processing

- Pillow
- Additional libraries only when justified

## Storage

- Local filesystem for image files
- SQLite for metadata and application state
- Application data stored separately from source code

## AI Integration

Use modular adapters for:

- Scene analysis
- Prompt generation
- Image generation
- Image editing
- Optional quality evaluation

## Development

- Codex Desktop
- Git
- Automated tests
- Project documentation
- Mandatory session continuity files

Prefer simple, maintainable solutions.

Avoid unnecessary infrastructure or dependencies.

---

# 4. PROJECT DIRECTORY STRUCTURE

Recommended structure:

character-studio/
|
|-- PLAN.md
|-- AGENTS.md
|-- README.md
|-- PROJECT_STATUS.md
|-- SESSION_HANDOFF.md
|-- CHANGELOG.md
|-- DECISIONS.md
|
|-- frontend/
|   |-- src/
|   |-- components/
|   |-- pages/
|   |-- services/
|
|-- backend/
|   |-- api/
|   |-- models/
|   |-- schemas/
|   |-- services/
|   |   |-- characters/
|   |   |-- groups/
|   |   |-- scene_analysis/
|   |   |-- prompt_engine/
|   |   |-- character_mapping/
|   |   |-- approvals/
|   |   |-- generations/
|   |   |-- evaluation/
|   |
|   |-- providers/
|   |   |-- analysis/
|   |   |-- generation/
|   |
|   |-- persistence/
|   |-- configuration/
|
|-- tests/
|-- scripts/
|-- docs/
|
|-- .gitignore

Private application data must be stored in a configurable
location OUTSIDE the source-code repository.

Example:

Character-Studio-Data/
|
|-- characters/
|-- scenes/
|-- generations/
|-- thumbnails/
|-- exports/
|-- jobs/          (per-run CLI engine job folders)
|-- backups/
|-- studio.db

Never commit personal reference photographs, generated
images containing private subjects, databases, API keys,
or other sensitive application data.

---

# 5. CHARACTER LIBRARY

The Character Library is the foundation of the application.

## 5.1 Character Profiles

Each character must support:

- Unique character ID
- Display name or alias
- Age category: Adult, Teen, Child
- Optional notes
- Multiple reference photographs
- Primary reference photograph
- Reference image labels
- Group memberships
- Created/updated timestamps

Avoid storing unnecessary sensitive personal information.

Character names must be supplied by the user.

Do not automatically identify unknown people.

## 5.2 Reference Photograph Management

Allow:

- Uploading multiple photographs
- Viewing photographs in a gallery
- Assigning reference labels
- Selecting the primary identity photograph
- Adding and removing supporting photographs
- Previewing full-size images
- Deleting selected reference images
- Reusing saved photographs across scenes

Suggested reference labels:

- Front
- Left three-quarter
- Right three-quarter
- Left profile
- Right profile
- Full body
- Additional

The system must not require all reference types.

Store original photographs without destructive editing.

Create separate thumbnails for display.

## 5.3 Reference Selection

The system should select a useful subset of saved
photographs for each image-generation request.

It should not automatically submit every photograph.

Selection may consider:

- Reference quality
- Visible facial characteristics
- Availability of complementary viewpoints
- Provider reference-image limits

Selection must never change the requested scene angle.

Allow manual reference overrides.

## 5.4 Character Management

Support:

- Create character
- Edit character
- Delete character
- Search characters
- View character details
- Manage character photographs
- Manage group membership

Deleting a character must not silently destroy
previous generation history.

Provide explicit deletion choices and explain
what data will be removed.

---

# 6. CHARACTER GROUPS

Support reusable groups containing multiple characters.

Examples:

- Couple
- Family
- Parents and children
- Custom group

Features:

- Create group
- Rename group
- Add/remove characters
- Delete group
- Select group during mapping

A character may belong to multiple groups.

Group membership must not automatically determine
subject positions within the Base Image.

The user must confirm subject assignments.

---

# 7. SCENE MANAGEMENT

## 7.1 Base Image Upload

Support:

- JPEG
- PNG
- WebP

Requirements:

- Validate file type and contents
- Enforce configurable file-size limits
- Store original images
- Generate preview thumbnails
- Record dimensions and aspect ratio
- Create unique scene IDs

## 7.2 Scene Library

Each scene must support:

- Title
- Base Image
- Analysis
- Structured scene data
- Prompt versions
- Subject mappings
- Approval history
- Generation history
- Saved workflow state

Features:

- Create scene
- Open scene
- Rename scene
- Duplicate scene
- Delete scene
- Resume unfinished scene

A scene must remain available after application restart.

---

# 8. SCENE ANALYSIS ENGINE

The analysis engine examines the Base Image and produces:

1. Brief visual analysis
2. Structured scene specification
3. Detailed generation prompt
4. Negative prompt

## 8.1 Required Analysis

Analyze:

- Number of visible people
- Subject positions
- Camera height and direction
- Shot type and framing
- Perspective and crop
- Torso orientation
- Shoulder alignment
- Head direction
- Facial viewing angle
- Eye direction and gaze
- Arms, hands, and legs
- Clothing and accessories
- Hairstyle
- Background objects
- Lighting and shadows
- Color palette
- Overall atmosphere

Explicitly distinguish:

- Camera direction
- Body direction
- Head direction
- Eye direction

## 8.2 Structured Analysis

Store the analysis as versioned JSON.

Suggested components:

- Image properties
- Scene description
- Camera properties
- Subject descriptions
- Pose descriptions
- Outfit descriptions
- Lighting information
- Environment information
- Composition constraints
- Uncertain observations

Avoid unsupported assumptions.

Where visual information is ambiguous, record
uncertainty rather than inventing details.

## 8.3 Analysis Provider

Use a modular "analysis engine" interface.

Two CLI engines are built in Phase 3, selectable in
Settings (DECISIONS.md D009):

- Claude Code CLI (`claude -p`) on the user's Claude
  Pro subscription (default)
- Codex CLI (`codex exec`) on the user's ChatGPT
  subscription; this uses the ChatGPT plan's Codex
  allowance, which may be shared with image generation

The interface must also allow adding a paid API-based
analysis engine later (post-MVP; see §12.3 and
Phase 6).

The manual analysis workflow (copy the fixed analysis
instruction, import the analysis) remains as the
fallback and must always be available.

Every engine run is started by an explicit user action.
No engine is an unattended background service, and no
run is retried automatically.

Exact CLI flags, output behaviour and failure modes
must be verified in Phase 2.5 before implementation.

By default, scene analysis and image generation use
different engines: Claude for analysis, Codex for
images.

---

# 9. SUBJECT DETECTION AND CHARACTER MAPPING

The application must identify visible subjects.

Assign temporary identifiers:

- Subject 1
- Subject 2
- Subject 3
- Etc.

Display the subject positions on the Base Image.

Support approximate subject bounding regions.

Allow the user to correct subject labels and regions.

## Subject Actions

For each subject:

- Replace with saved character
- Keep original subject unchanged
- Leave assignment unresolved

## Multi-Character Requirements

Maintain identity separation.

Prevent accidental mapping confusion.

Allow users to map different saved characters
to individual people in the Base Image.

For example:

Subject 1 -> Character A
Subject 2 -> Character B
Subject 3 -> Keep Original

Subject mapping must remain editable until approval.

---

# 10. PROMPT GENERATION ENGINE

Generate one comprehensive, editable image-generation prompt.

The prompt must include:

1. Base Image composition instructions
2. Camera angle and perspective
3. Framing and cropping
4. Subject positions
5. Individual poses
6. Head and gaze directions
7. Clothing and accessories
8. Environment and lighting
9. Character identity assignments
10. Identity-lock instructions
11. Composition-lock instructions
12. Negative instructions

## Required Identity Lock

Use the selected Character Reference photographs
solely to establish the corresponding person's identity.

Do not copy their original poses, camera angles,
expressions, or backgrounds.

## Required Composition Lock

Reproduce the Base Image's visual composition as
faithfully as possible.

Preserve the intended pose, viewing angle, body
orientation, head rotation, gaze, framing, outfit,
environment, and lighting.

## Prompt Features

- View prompt
- Edit prompt
- Copy prompt
- Save prompt version
- Restore earlier versions
- Edit negative prompt
- Regenerate draft prompt
- Add explicit scene modifications

Changing character assignments should preserve
the underlying scene analysis.

Do not unnecessarily reanalyze the Base Image.

---

# 11. USER APPROVAL WORKFLOW

Approval is mandatory before image generation.

## Review Screen

Display:

- Base Image
- Scene analysis
- Identified subjects
- Character assignments
- Selected reference photographs
- Full generation prompt
- Negative prompt
- Provider selection
- Generation settings
- Available cost information

Allow the user to modify everything before approval.

## Approval Snapshot

Approval must create an immutable record containing:

- Scene version
- Base Image reference
- Prompt version
- Negative prompt
- Subject mappings
- Selected character references
- Model/settings
- Approval timestamp

Use stable identifiers and content hashes where useful.

If any approved input changes, approval becomes invalid.

The approval covers content, not the engine
(decided 2026-10-10). The same valid approval may be
used with the Codex engine or the manual bridge
(including "Export for manual use" after a failed
Generate) and survives changing the generation engine
in Settings. Each generation job records the engine
and version that actually ran. A future paid API
engine must additionally ask for explicit cost
confirmation on every run; approval alone never starts
a paid request.

Do not generate using stale approval records.

## Approval Rule

No image-generation request may start unless the
user has explicitly approved the corresponding inputs.

Paid operations must not begin silently.

---

# 12. GENERATION PROVIDER SYSTEM

Build interchangeable generation adapters.

Conceptual interface:

generate_image(
    approved_scene,
    character_mappings,
    selected_references,
    generation_settings
) -> generation_result

Each adapter must declare:

- Provider name
- Available capabilities
- Supported image formats
- Multiple-reference support
- Image-editing support
- Mask support
- Resolution options
- Relevant limits
- Pricing information, if available

## 12.1 CLI Engines (Main Path)

Decision: DECISIONS.md D009.

The studio runs the official command-line tools that
the user has installed and signed into on this PC:

- Analysis and "Polish prompt": Claude Code CLI
  (`claude -p`) on the user's Claude Pro subscription
- Analysis (user-selectable alternative): Codex CLI
  (`codex exec`)
- Image generation: Codex CLI (`codex exec` with its
  built-in image generation) on the user's ChatGPT
  subscription (Plus or above)

Rules:

- No API keys and no per-use billing. Each run uses
  the relevant plan's usage allowance.
- Only the official `claude` and `codex` programs.
- Never read, copy, store or forward their login
  tokens or credential files.
- No third-party gateways (for example OmniRoute) and
  no extraction of subscription credentials into
  other tools.
- No browser automation or scripting against
  chatgpt.com or claude.ai.
- No unofficial endpoints.
- Each run is started by an explicit user action, runs
  in its own job folder, has a timeout and a cancel
  option, and is never retried automatically.
- Record the engine name and CLI version with every
  analysis, prompt version and generation it produces.
- Confine each run's file access to its job folder
  using the CLI's own permission/sandbox options where
  Phase 2.5 confirms they exist. Where none exist, the
  limitation is recorded in docs/PROVIDER_FINDINGS.md
  and the engine may still be used (decided
  2026-10-10).
- Job statuses: Failed (the CLI reported an error),
  Cancelled (the user clicked Cancel), Interrupted (the
  studio stopped mid-run). An Interrupted run may
  already have used allowance or saved an output; the
  UI asks the user to check its job folder before
  "Try again". Nothing is ever resubmitted
  automatically.

Before implementation, Phase 2.5 must verify and record
in docs/PROVIDER_FINDINGS.md:

- Installed versions and sign-in state of both CLIs
- The exact flags that actually exist (from `--help`)
- Where generated images are saved
- Timings and how failures appear (signed out, usage
  limit reached, timeout, malformed output)
- Whether each CLI can confine file access to a folder
- Whether attached reference photos keep each person's
  likeness (user's judgement)

Do not assume flags or output locations that the spike
has not confirmed.

## 12.2 Manual Bridge Provider (Fallback)

This fallback must be supported. It is offered whenever
a CLI engine is unavailable or fails, and can be chosen
as the engine in Settings.

Allow exporting a complete generation package:

- Base Image
- Selected character references
- Approved prompt
- Negative prompt
- Character mapping manifest
- Relevant generation settings

Allow importing externally generated images.

Connect imported results to their original scene
and approval snapshot.

Use this workflow with ChatGPT Images, Codex or other
compatible interfaces when the CLI engines are
unavailable, fail, or the user prefers manual use.

## 12.3 OpenAI Image API Provider

Optional integration. Stays off and is unchanged
by D009.

Planned post-MVP (user direction, 2026-10-10): the
application will eventually offer paid API-based
engines for BOTH scene analysis and image generation,
selectable alongside the CLI and manual engines. They
are off by default, need separate explicit approval to
build, and every paid run needs explicit cost
confirmation. Design the engine interfaces so these
can be added without restructuring.

Requirements:

- API key configuration
- Separate billing awareness
- Reference-image inputs
- Image-editing support where available
- Error handling
- Output persistence
- Configurable supported model/settings
- Usage and cost metadata where available

Verify current official API capabilities before
implementation.

Do not assume ChatGPT Plus includes API credits.

Avoid hardcoding unverified model names or limits.

---

# 13. GENERATION STRATEGY

Prefer using the Base Image as a visual reference,
not merely describing it with text.

Where supported, use image editing instead of fully
recreating the entire image from scratch.

Priorities:

1. Preserve subject positions
2. Preserve camera perspective
3. Preserve poses
4. Preserve head and gaze directions
5. Preserve outfits
6. Preserve environment
7. Preserve lighting
8. Replace intended identities

For group images:

- Maintain correct identity-to-subject mappings
- Avoid identity blending
- Preserve relative positions
- Keep unchanged subjects unchanged where possible

Exact visual reproduction cannot be guaranteed.

Do not misrepresent model accuracy.

Support region-based editing later when appropriate.

---

# 14. GENERATION HISTORY AND RESULTS

Every generation record must contain:

- Generation ID
- Scene ID
- Approved input snapshot
- Prompt version
- Character mapping
- Reference image IDs
- Provider and model
- Generation settings
- Output file path
- Creation timestamp
- Job status
- Error details, if applicable

## Result Features

- View generated image
- Compare with Base Image
- Save multiple versions
- Select preferred result
- Request regeneration
- Revise prompt
- Reuse settings
- Export image
- Import externally generated result

Never overwrite earlier results.

Keep each image connected to the exact inputs
used for its generation.

---

# 15. MANDATORY SESSION CONTINUITY SYSTEM

This section is a CORE architectural requirement.

The project must support reliable pause/resume behavior
for both:

A. Codex development sessions
B. Character Studio application workflows

Do not rely solely on conversation history.

---

# 16. CODEX DEVELOPMENT SESSION CONTINUITY

Maintain the following files in the project root.

## 16.1 PLAN.md

Purpose:

The authoritative project requirements and architecture.

Contains:

- Project vision
- Technology decisions
- Module specifications
- Implementation phases
- Acceptance criteria
- Continuity requirements

Do not silently modify requirements.

Significant changes require user approval.

## 16.2 PROJECT_STATUS.md

Purpose:

Quick overview of the current project state.

Must record:

- Current development phase
- Overall progress
- Completed milestones
- Active tasks
- Pending tasks
- Known blockers
- Latest verified test status
- Immediate next recommended action
- Last checkpoint date/time

This file should be concise and easy to scan.

## 16.3 SESSION_HANDOFF.md

Purpose:

Allow any new Codex session to resume accurately.

Must include:

- Last session objective
- Work completed
- Files changed
- Work currently in progress
- Unfinished tasks
- Known errors or blockers
- Commands/tests executed
- Test results
- Current Git state
- Relevant commit identifier
- Required next steps
- Any approval needed from the user

This is the primary resume checkpoint.

Do not fill it with unnecessary conversation history.

## 16.4 CHANGELOG.md

Purpose:

Chronological record of meaningful project changes.

Record:

- Implemented features
- Bug fixes
- Refactoring
- Database changes
- Major configuration changes
- Important testing milestones

Do not log every trivial edit.

Use dated entries.

## 16.5 DECISIONS.md

Purpose:

Architectural decision log.

Record:

- Decision
- Date
- Reason
- Alternatives considered
- Consequences
- Whether the user approved it

Important decisions must remain available even when
the original Codex conversation is no longer accessible.

## 16.6 AGENTS.md

Purpose:

Concise, persistent instructions for Codex.

During Phase 1, create AGENTS.md containing rules to:

- Read PLAN.md before major work
- Read PROJECT_STATUS.md at session start
- Read SESSION_HANDOFF.md before resuming
- Respect existing architectural decisions
- Check Git status before editing
- Preserve uncommitted user changes
- Update documentation at milestone boundaries
- Run relevant tests
- Record blockers accurately
- Avoid unauthorized scope changes
- Create checkpoints when requested
- Never fabricate completion or test results

Keep AGENTS.md short and operational.

Do not duplicate the entire PLAN.md.

---

# 17. DEVELOPMENT CHECKPOINT PROTOCOL

Codex must maintain reliable checkpoints.

## When to Create a Checkpoint

Create/update a checkpoint:

- After completing a development milestone
- Before a planned pause
- Before a major architectural change
- After resolving a significant blocker
- Whenever the user says "Checkpoint"
- Whenever the user asks to stop development

## Checkpoint Procedure

1. Inspect current repository state.
2. Identify completed work.
3. Identify unfinished changes.
4. Run relevant tests when feasible.
5. Record actual test results.
6. Update PROJECT_STATUS.md.
7. Update SESSION_HANDOFF.md.
8. Update CHANGELOG.md if meaningful changes occurred.
9. Update DECISIONS.md if architecture changed.
10. Summarize the exact next action.

Checkpoint files should be written atomically where
practical to avoid partially written documents.

Do not claim a test passed unless it actually ran.

Do not claim a Git commit exists unless verified.

## Git Rules

Use Git for source-code version history.

- Make commits at meaningful checkpoints.
- Respect user approval requirements for commits.
- Never discard uncommitted changes without permission.
- Never force-push or rewrite history automatically.
- Never commit secrets, character photographs,
  personal data, or generated private images.

Documentation checkpoints and Git checkpoints
complement each other.

They are not substitutes for one another.

Unexpected shutdowns may occur before a checkpoint.
The resume protocol must detect unfinished work.

---

# 18. CODEX SESSION RESUME PROTOCOL

When the user starts a new Codex conversation and says:

"Resume Character Studio"

Codex must:

1. Read PLAN.md.
2. Read AGENTS.md.
3. Read PROJECT_STATUS.md.
4. Read SESSION_HANDOFF.md.
5. Review relevant CHANGELOG.md entries.
6. Review relevant DECISIONS.md entries.
7. Inspect the current project files.
8. Check Git status and recent commits.
9. Detect unfinished or uncommitted changes.
10. Compare documented progress with actual files.
11. Identify blockers or inconsistencies.
12. Summarize the current verified state.
13. Identify the next recommended task.

Codex must not assume that checkpoint documentation
perfectly reflects the repository.

Actual files and verified Git state must be checked.

If documentation and repository state disagree,
report the difference and request clarification
before taking destructive action.

Resume work according to existing approval rules.

A resume instruction is not blanket permission to
perform destructive changes or paid operations.

Do not repeat completed work unnecessarily.

---

# 19. APPLICATION-LEVEL PAUSE AND RESUME

Character Studio itself must support workflow recovery.

## Persisted State

Save:

- Base Images
- Scene records
- Scene analyses
- Prompt drafts and versions
- Character assignments
- Selected reference images
- User edits
- Approval snapshots
- Generation jobs
- Generated results
- Current workflow stage

## Resume Behavior

When the user reopens Character Studio:

- Show recent scenes
- Show unfinished scenes
- Allow opening the last active scene
- Restore saved analysis and mappings
- Restore prompt edits
- Restore valid approval status
- Show previous generation results
- Allow continuation from the saved stage

Normal navigation or closing the browser should
not discard persisted work.

Use server-side persistence rather than depending
only on browser memory.

Save meaningful edits reliably.

## Interrupted Generation Jobs

An interrupted generation job must not be
automatically resubmitted.

Distinguish:

- Pending
- Running
- Completed
- Failed
- Cancelled
- Interrupted
- Outcome Unknown

If the application restarts while a paid request
was in progress, attempt provider-supported status
reconciliation when possible.

Do not assume a request failed merely because
the local process stopped.

Do not repeat a paid request until the user confirms.

Use request identifiers and idempotency mechanisms
where supported by the provider.

Explain possible duplicate billing risks.

## Approval Recovery

Persist approvals as immutable snapshots.

A valid approval may remain valid after restarting
the application if all approved inputs are unchanged.

Any change to approved inputs must invalidate approval.

---

# 20. DATA MODEL

Use SQLite with versioned migrations.

Core entities:

## Character

- id
- display_name
- age_category
- notes
- created_at
- updated_at

## CharacterReference

- id
- character_id
- file_path
- content_hash
- view_label
- is_primary
- created_at

## CharacterGroup

- id
- name
- created_at

## CharacterGroupMember

- group_id
- character_id

## Scene

- id
- title
- base_image_path
- workflow_state
- created_at
- updated_at

## SceneAnalysis

- id
- scene_id
- schema_version
- structured_analysis
- analysis_text
- version
- source (claude_cli / codex_cli / manual_import)
- engine_version (CLI version, if any)
- raw_output_path (job-folder file, if any)
- created_at

## SceneSubject

- id
- scene_id
- label
- bounding_region
- description

## SubjectMapping

- id
- scene_id
- scene_subject_id
- character_id (nullable)
- mapping_action

## PromptVersion

- id
- scene_id
- prompt_text
- negative_prompt
- version
- is_polished (true when produced by "Polish prompt")
- polished_from_version_id (nullable)
- engine_version (if polished)
- created_at

## Approval

- id
- scene_id
- snapshot_json
- snapshot_hash
- approved_at
- invalidated_at

## GenerationJob

- id
- approval_id
- provider
- model
- settings_json
- provider_request_id
- engine_version (CLI version, if any)
- job_folder (relative path, if any)
- status
- error_kind / error_details (if any)
- created_at
- updated_at

## GenerationResult

- id
- generation_job_id
- output_path
- version
- user_rating
- created_at

## WorkflowCheckpoint

- id
- scene_id
- workflow_state
- relevant_version_ids
- saved_at

Schema details may be refined during implementation.

Use proper foreign keys, indexes, transactions,
and migration procedures.

Do not store large image binaries inside SQLite.

---

# 21. USER INTERFACE

Required screens:

1. Dashboard
2. Character Library
3. Character Profile
4. Character Groups
5. New Scene
6. Scene Analysis
7. Subject Mapping
8. Prompt Review
9. Generation Workspace
10. Results Gallery
11. Settings

## Dashboard

Show:

- Recent scenes
- Unfinished scenes
- Saved characters
- Latest results
- Available generation providers

Provide a "Resume Last Scene" action.

## UX Principles

- Image-first design
- Minimal technical complexity
- Clear step-by-step workflow
- Responsive layouts
- Easy character selection
- Editable prompts
- Visible approval status
- Clear loading and error messages
- No silent paid operations
- Easy pause/resume
- Easy recovery from interruptions

The user should not need a terminal for everyday
image-generation operations.

---

# 22. PRIVACY AND SECURITY

The system is local-first.

Requirements:

- Store private images locally by default.
- Bind the local backend to 127.0.0.1 by default.
- Do not expose the server publicly.
- Protect against unsafe file paths and uploads.
- Validate actual file contents.
- Handle image metadata carefully.
- Remove unnecessary location metadata from
  images sent to external providers.
- Keep API secrets outside source code.
- Never expose secrets to the frontend.
- Restrict cross-origin access appropriately.
- Never include private photographs in Git.
- Avoid sensitive data in logs.
- Allow users to delete their data.
- Provide backup and restore functionality.
- Document which operations send images externally.
  With the CLI engines: "Analyse" sends the Base Image
  to Anthropic via Claude Code (or to OpenAI via Codex
  when Codex is the analysis engine); "Polish prompt" sends
  prompt and analysis text (no images) to Anthropic;
  "Generate" sends the Base Image and selected
  reference photos to OpenAI via Codex.
- Never read, copy, store, log or forward the CLI
  tools' login tokens or credential files.
- Job folders live in the private data directory,
  never in the repository.

For children's photographs:

- Use appropriate, authorized reference images.
- Preserve age-appropriate presentation.
- Avoid unnecessary sensitive personal details.
- Do not generate exploitative or sexualized content.
- Apply provider safety requirements.

Do not identify unknown people through external
face-recognition databases.

## Backup and Restore

Backups must include:

- Database
- Character references
- Scene files
- Prompts and mappings
- Generation history
- Relevant metadata

Backups must be consistent and restorable.

Avoid copying a live SQLite database unsafely.

Use supported SQLite backup procedures.

Provide clear restore instructions.

Support optional encrypted backups later.

---

# 23. ERROR HANDLING AND RECOVERY

The application must handle:

- Invalid image uploads
- Corrupted image files
- Missing reference photographs
- Missing characters
- Invalid subject mappings
- Analysis failures
- Provider unavailability
- API authentication errors
- Rate limits
- Network interruptions
- Generation failures
- Application restarts
- Incomplete jobs
- Database errors

Errors must be visible and understandable.

Do not silently delete failed work.

Preserve recoverable inputs.

Never retry paid generation blindly.

---

# 24. IMPLEMENTATION ROADMAP

Implementation must proceed in phases.

Each phase must have clear deliverables, tests,
and completion criteria.

Do not begin a subsequent phase automatically
without user approval.

## PHASE 0 — DISCOVERY AND PLANNING

Tasks:

- Review PLAN.md
- Inspect development environment
- Verify available Codex tools
- Verify actual image-generation capabilities
- Identify available scene-analysis options
- Evaluate integration limitations
- Validate technology choices
- Identify required dependencies
- Review privacy and cost implications
- Propose refined implementation milestones

Deliverable:

A verified technical implementation plan.

No application coding during Phase 0.

User approval required before Phase 1.

## PHASE 1 — FOUNDATION AND CONTINUITY

Tasks:

- Initialize repository
- Create frontend/backend skeleton
- Configure SQLite
- Configure local data storage
- Establish provider interfaces
- Establish configuration management
- Add baseline tests
- Create AGENTS.md
- Create PROJECT_STATUS.md
- Create SESSION_HANDOFF.md
- Create CHANGELOG.md
- Create DECISIONS.md
- Establish Git checkpoint practices
- Document resume and checkpoint procedures

Acceptance:

- Application launches locally
- Backend/frontend communicate
- Database persists information
- Continuity files exist
- Checkpoint procedure works
- New Codex sessions can recover project status
- Basic tests pass

## PHASE 2 — CHARACTER LIBRARY

Tasks:

- Character CRUD
- Reference image uploads
- Primary photo selection
- Image labels
- Character groups
- Search functionality
- Thumbnail generation
- Persistent character storage

Acceptance:

- Characters can be created and edited
- Multiple photos are supported
- Photos remain after application restart
- Character references are reusable
- Basic privacy safeguards work

## PHASE 2.5 — ENGINE VERIFICATION SPIKE

Purpose: verify the CLI engines (DECISIONS.md D009)
before Phase 3 work. Small throwaway tests only; no
application code. Write a short dated result in
docs/PROVIDER_FINDINGS.md. Use synthetic or authorized
images; keep test images, outputs and logs outside the
repository.

Tasks:

a. Installation and sign-in
   - Check that `claude` and `codex` are installed and
     signed in. Record their versions.
   - Confirm the exact flags with `claude --help` and
     `codex exec --help`. Do not assume flags; record
     only the ones that actually exist.
   - Check each CLI's permission/sandbox options for
     confining file access to a single folder. Record
     what exists; if nothing does, record it as a known
     limitation (not a blocker).

b. Claude analysis test
   - Run `claude -p` non-interactively on a sample
     scene image, allowing only the Read tool, asking
     for the analysis in the studio's JSON format.
   - Record whether the JSON comes back clean, how long
     it takes, and how failures look (signed out, usage
     limit reached, bad JSON).

b2. Codex analysis test
   - Run `codex exec` non-interactively on the same
     sample scene image with the same analysis
     instruction and JSON format, read-only.
   - Record the same items as (b), so the two engines
     can be compared.

c. Codex generation test
   - Run `codex exec` with a base image plus 2–3
     reference photos of one person and a prompt from
     the planned template.
   - Record where the generated file is saved, how long
     it takes, and how failures look.
   - The user judges whether the likeness is
     acceptable.

d. Likeness is a quality check, not a gate
   - Per the user, OpenAI's documentation confirms
     Codex image generation with reference photos and
     identity preservation. Find and cite the exact
     official OpenAI page in docs/PROVIDER_FINDINGS.md
     (documentation reading only).
   - Record test (c)'s result, but proceed with the
     Codex-based Generate design either way. The manual
     bridge stays as the fallback.

Gate (decided 2026-10-10): Generate (Phase 5) and the
CLI analysis engines (Phase 3) are built only on
mechanics the spike confirmed: real flags, output
locations and failure appearances. The user's likeness
verdict is recorded but does not block Generate.

Deliverable:

- Dated spike results in docs/PROVIDER_FINDINGS.md:
  versions, confirmed flags, commands used, output
  locations, timings, failure appearances, file-access
  confinement options, the cited OpenAI documentation
  page, and the user's likeness verdict.

Approval: start only after the user says
"Approve Phase 2.5". Phase 3 requires its own approval.

## PHASE 3 — SCENE ANALYSIS

Tasks:

- Base Image upload
- Scene creation
- Scene analysis integration
- Structured JSON analysis
- Detailed prompt generation
- Negative prompt generation
- Prompt editing
- Analysis versioning
- Scene save/resume
- "Analyse" button using the analysis engine interface
- Manual analysis fallback (copy instruction, import
  analysis)
- Engine settings and status (below)

### Analyse with an engine

- An "Analyse" button on a scene runs analysis through
  the analysis engine interface, using the engine
  selected in Settings. Two CLI engines are built:
  Claude Code CLI (default) and Codex CLI. The design
  must also allow a paid API engine to be added
  post-MVP.
- Each run creates a job folder in the private data
  directory, for example
  `Character-Studio-Data\jobs\<scene>\analysis-<n>\`.
- Copy the Base Image into the job folder (with
  location metadata removed, per §22).
- Claude: run `claude -p` with the fixed analysis
  instruction, the working directory set to the job
  folder, only the Read tool allowed, no network tools,
  and a timeout.
- Codex: run `codex exec` with the same fixed
  instruction, the job folder as working directory,
  read-only, and a timeout.
- For both: use only flags confirmed in Phase 2.5, and
  confine file access to the job folder where Phase 2.5
  confirmed an option for it.
- Capture the output to a file in the job folder.
- Validate the result against the same schema the
  manual "Import analysis" uses. Flag uncertain items
  for the user to confirm, exactly as in the manual
  flow.
- Save the raw output and the engine/version used with
  the analysis record.
- The prompt is still built by the studio's own
  template from the validated analysis. The analysis
  engine does not write the main prompt.
- The prompt template labels attached images by number
  (Base Image and each reference photo) and uses
  "Subject N" labels, so later polishing and
  generation can reference them reliably.

### Analysis UI

- Progress state naming the engine ("Analysing with
  Claude…" / "Analysing with Codex…") with a Cancel
  button.
- Clear error messages for: CLI not installed, signed
  out, usage limit reached, timeout, invalid format.
- Each error offers "Try again" and "Do it manually"
  (the copy-instruction + import-analysis flow).
- Failed / Cancelled / Interrupted statuses as in
  §12.1.
- Never retry automatically.

### Engine settings

- Engine status: show whether `claude` and `codex` are
  found and signed in, with a "Check again" button.
  Never read or store credentials.
- Analysis engine choice: Claude (default), Codex, or
  Manual. Both CLI engines are fully selectable; the
  Codex option notes that it uses the ChatGPT plan's
  allowance.
- Generation engine choice: Codex (default) or Manual.
- Timeout per engine.

Acceptance:

- Scenes can be analyzed via the Claude CLI engine,
  the Codex CLI engine or the manual import, all
  validated by the same schema
- Engine errors are clearly reported and offer a
  manual fallback; nothing retries automatically
- Raw output and engine/version are stored with each
  analysis
- Prompts can be saved and edited
- Scene state persists after restart
- Uncertain analysis details can be corrected

## PHASE 4 — CHARACTER MAPPING AND APPROVAL

Tasks:

- Subject identification
- Subject markers
- Character assignment
- Group selection
- Reference photo selection
- Prompt review screen
- Approval snapshots
- Approval invalidation
- Workflow persistence
- Optional "Polish prompt"

### Polish prompt (optional)

- A "Polish prompt" button on the review screen,
  available before approval.
- Sends Claude (via `claude -p`, text only, no tools)
  the template prompt and the scene analysis, with
  fixed rules: keep every fact, add nothing new, keep
  the "Subject N" labels, image numbers and identity
  instructions, keep any "keep original unchanged"
  lines, and return only the prompt text.
- Show the original and polished prompts side by side
  with the differences highlighted. Choices: "Use
  polished", "Keep original", or edit by hand.
- Before accepting, the studio checks that the
  required elements are still present: every subject
  mapping, every "keep original" instruction, and the
  image-number references. If any are missing, warn
  the user and do not accept automatically.
- Save the polished prompt as a new prompt version.
  Both versions are kept, with a flag recording which
  was polished.
- Approval locks whichever version the user chose.
  Polishing after approval cancels the approval, like
  any other edit.
- Same error handling as Analyse (progress, cancel,
  clear messages, no automatic retry); on failure the
  original prompt is unchanged.

Acceptance:

- Multiple people can be mapped
- Mappings are editable
- Approval blocks unauthorized generation
- Changing inputs invalidates approval
- Approved states survive restart correctly
- A polished prompt is only accepted when all required
  elements are present or the user explicitly accepts
  after a warning; both versions remain stored

## PHASE 5 — GENERATION AND RESULTS

Tasks:

- Implement verified generation integration
  ("Generate" via the Codex CLI)
- Implement manual bridge fallback
- Add optional API adapter
- Generation job handling
- Result gallery
- Image comparisons
- Generation history
- Output versioning
- Interrupted job handling

### Generate (Codex CLI)

- A "Generate" button, available only from a valid
  approval.
- It builds the same export package as the manual
  bridge (Base Image, chosen reference photos with
  location data removed, prompt.txt,
  negative_prompt.txt, mapping.txt) into a job folder.
- It then runs `codex exec` with those images attached
  and the prompt, using built-in image generation, with
  the method and flags confirmed in Phase 2.5.
- Pick up the generated image from wherever Phase 2.5
  showed Codex saves it, copy it into results, and link
  it to this scene and this approval automatically, the
  same as "Import result". Never overwrite earlier
  results.
- "Generate again" and "Variation" each create a new
  result.
- Failed, Cancelled and Interrupted generations are
  marked with those distinct statuses (§12.1) and never
  resubmitted automatically. An Interrupted generation
  asks the user to check its job folder for a saved
  image before "Generate again".
- The approval covers content, not the engine (§11):
  "Export for manual use" works under the same valid
  approval.
- Errors (CLI missing, signed out, plan limit reached,
  timeout, no image produced) show a clear message and
  offer "Export for manual use" (the existing manual
  package flow).
- The UI notes that each attempt uses the ChatGPT
  plan's image allowance.

Acceptance:

- Approved scenes can be generated via the Codex CLI
  or exported through the manual bridge
- Generated results are linked to their scene and
  approval automatically
- Results can be imported and saved
- Previous versions remain available
- Failed/interrupted jobs are recoverable
- No automatic duplicate paid requests or automatic
  resubmission of generations

## PHASE 6 — QUALITY AND ADVANCED FEATURES

Optional improvements:

- Region-based editing
- Selective identity replacement
- Identity consistency checks
- Composition fidelity checks
- Multiple image variations
- Saved generation presets
- Batch generation
- Advanced comparison interface
- Additional generation providers
- Optional paid API-based engines for scene analysis
  and image generation (off by default, separate
  explicit approval, per-run cost confirmation; §12.3)
- Encrypted backups

Implement only after the core application works.

---

# 25. TESTING STRATEGY

Include automated tests for:

- Character creation/editing/deletion
- Reference image persistence
- File validation
- Character groups
- Scene persistence
- Analysis data validation
- Prompt versioning
- Character mapping
- Approval enforcement
- Approval invalidation
- Generation provider capability checks
- Generation job state transitions
- Interrupted job recovery
- Data backup and restore
- Session continuity documentation

## Image Workflow Test Cases

1. Single adult subject
2. Side-profile scene
3. Two-person couple
4. Family with adults and children
5. Partial character replacement
6. Scene with unchanged subjects
7. Interrupted generation job
8. Application restart during an unfinished scene

Use synthetic or authorized test images.

Do not commit private family photos to the repository.

Separate software correctness from visual-generation
quality assessment.

Passing application tests does not guarantee perfect
identity or pose reproduction.

---

# 26. CODEX OPERATING RULES

Codex must:

1. Read PLAN.md before major implementation decisions.
2. Respect the approved project architecture.
3. Read continuity files when starting new sessions.
4. Inspect the actual repository before claiming progress.
5. Make incremental, testable changes.
6. Run relevant tests when feasible.
7. Report actual test outcomes.
8. Update continuity records at milestone boundaries.
9. Preserve unfinished work.
10. Never silently delete or overwrite user data.
11. Avoid unnecessary dependencies.
12. Avoid undocumented APIs.
13. Keep private data outside Git.
14. Request approval before major architecture changes.
15. Request approval before moving to the next phase.
16. Clearly report technical blockers.
17. Avoid falsely claiming work is complete.
18. Maintain useful developer documentation.
19. Never initiate paid image generation without approval.
20. Treat PLAN.md as the primary requirements document.

Codex should minimize redundant explanations and provide
clear summaries of progress, blockers, and next actions.

---

# 27. DEFINITION OF SUCCESS

The initial product is successful when the user can:

1. Open Character Studio locally.
2. Create named character profiles.
3. Save multiple reference photos per character.
4. Organize characters into groups.
5. Upload a Base Image.
6. Generate a detailed scene prompt.
7. Assign saved identities to subjects.
8. Review and approve the mappings and prompt.
9. Generate an image from inside the studio via the
   Codex CLI, or export/import through the manual
   bridge as a fallback.
10. Compare results with the Base Image.
11. Save generations and prompt versions.
12. Close the application and resume later.
13. Resume Codex development in a new conversation.
14. Recover from interruptions without losing
    completed project work.

---

# 28. FIRST CODEX SESSION INSTRUCTIONS

The first Codex session must:

1. Read this entire PLAN.md.
2. Inspect the local environment.
3. Verify supported Codex capabilities.
4. Investigate supported image-generation integrations.
5. Identify limitations and unknowns.
6. Recommend improvements to the proposed architecture.
7. Produce a practical implementation roadmap.
8. Identify the minimum viable product.
9. Explain risks and possible API costs.
10. Wait for explicit user approval.

Do not start application implementation.

Do not install dependencies.

Do not initialize or modify project files without
explicit permission during the initial planning review.

Do not assume unavailable tools exist.

The user must approve Phase 1 before development begins.

---

# 29. STANDARD DEVELOPMENT COMMANDS

The following natural-language instructions should be
supported through the Codex operating procedures.

## "Checkpoint Character Studio"

Codex should:

- Review current work
- Update continuity documentation
- Record test results
- Record repository state
- Summarize the next steps

## "Resume Character Studio"

Codex should:

- Read continuity files
- Check actual repository state
- Identify unfinished work
- Summarize current progress
- Continue only within approved scope

## "Show Character Studio Status"

Codex should:

- Read PROJECT_STATUS.md
- Verify the current state
- Present completed work, blockers, and next steps

## "Prepare for Next Phase"

Codex should:

- Review completion criteria
- Verify tests
- Summarize the completed phase
- Present the next phase plan
- Request approval before implementation

---

# 30. FINAL PROJECT PRINCIPLES

Character Studio must be:

- Local-first
- Private by default
- Easy to use
- Modular
- Maintainable
- Reusable
- Approval-controlled
- Recoverable
- Transparent about limitations
- Flexible across image-generation providers

The ultimate goal is to let the user recreate scenes
with any saved character or group while minimizing
repetitive uploads, manual prompt writing, and setup.

Development continuity is a fundamental requirement,
not an optional feature.

END OF MASTER PLAN