from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StudioPreferences(Base):
    __tablename__ = "studio_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_preferences"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    studio_name: Mapped[str] = mapped_column(String(60), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    age_category: Mapped[str] = mapped_column(String(10))
    notes: Mapped[str] = mapped_column(Text)
    primary_photo_id: Mapped[str | None] = mapped_column(String(32))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ReferencePhoto(Base):
    __tablename__ = "reference_photos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    label: Mapped[str] = mapped_column(String(30))
    original_path: Mapped[str] = mapped_column(String(100))
    thumbnail_path: Mapped[str] = mapped_column(String(100))
    media_type: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    # Avatar framing: focus point (0-1 across the overflow) and zoom; display-only.
    frame_x: Mapped[float] = mapped_column(Float, default=0.5)
    frame_y: Mapped[float] = mapped_column(Float, default=0.3)
    frame_zoom: Mapped[float] = mapped_column(Float, default=1.0)
    # SHA-256 of the unchanged original; set on upload, backfilled at startup.
    content_hash: Mapped[str | None] = mapped_column(String(64))


class CharacterGroup(Base):
    __tablename__ = "character_groups"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class GroupMember(Base):
    __tablename__ = "group_members"
    group_id: Mapped[str] = mapped_column(ForeignKey("character_groups.id"), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), primary_key=True)


class PendingFileDeletion(Base):
    __tablename__ = "pending_file_deletions"
    path: Mapped[str] = mapped_column(String(100), primary_key=True)


class EngineSettings(Base):
    __tablename__ = "engine_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_engine_settings"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_engine: Mapped[str] = mapped_column(String(20))
    generation_engine: Mapped[str] = mapped_column(String(20))
    claude_timeout: Mapped[int] = mapped_column(Integer)
    codex_timeout: Mapped[int] = mapped_column(Integer)
    # API engines (Phase 6): one time limit and the chosen model per engine and purpose,
    # e.g. {"gemini_api": {"analysis": "gemini-2.5-flash"}}. Keys live in backend.keystore.
    api_timeout: Mapped[int] = mapped_column(Integer)
    api_models_json: Mapped[str] = mapped_column(Text)
    # Model lists fetched with the user's API keys (free list calls), kept between visits.
    model_lists_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer)


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    original_path: Mapped[str] = mapped_column(String(100))
    thumbnail_path: Mapped[str] = mapped_column(String(100))
    media_type: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    workflow_state: Mapped[str] = mapped_column(String(30))
    duplicated_from: Mapped[str | None] = mapped_column(String(32))
    # Group last chosen to narrow the character pickers; never assigns anyone by itself.
    mapping_group_id: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    last_opened_at: Mapped[str | None] = mapped_column(String(40))


class SceneAnalysis(Base):
    __tablename__ = "scene_analyses"
    __table_args__ = (UniqueConstraint("scene_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    structured_analysis: Mapped[str] = mapped_column(Text)
    analysis_text: Mapped[str] = mapped_column(Text)
    # Uncertainties the user confirmed; kept beside the schema-strict analysis JSON.
    confirmed_uncertainties: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    engine_version: Mapped[str | None] = mapped_column(String(80))
    raw_output_path: Mapped[str | None] = mapped_column(String(200))
    based_on_id: Mapped[str | None] = mapped_column(String(32))
    job_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(40))


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("scene_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("scene_analyses.id"))
    version: Mapped[int] = mapped_column(Integer)
    prompt_text: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text)
    scene_changes: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    is_polished: Mapped[bool] = mapped_column(Boolean, default=False)
    polished_from_version_id: Mapped[str | None] = mapped_column(String(32))
    engine_version: Mapped[str | None] = mapped_column(String(80))
    # Character assignments the template draft was built for (workflow.mapping_hash).
    mapping_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class EngineJob(Base):
    """One CLI engine run. Queue-ready: several may wait as not_started (D010)."""

    __tablename__ = "engine_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    engine: Mapped[str] = mapped_column(String(20))
    engine_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(32), index=True)
    # Order inside its batch; batch items wait as not_started until their turn (Phase 5.5).
    batch_position: Mapped[int | None] = mapped_column(Integer)
    job_folder: Mapped[str | None] = mapped_column(String(200))
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    error_kind: Mapped[str | None] = mapped_column(String(30))
    error_details: Mapped[str | None] = mapped_column(Text)
    result_id: Mapped[str | None] = mapped_column(String(32))
    # Polish runs: the prompt version polished, the candidate text and the user's choice.
    # Generation runs and manual exports use input_id for the approval they were made from.
    input_id: Mapped[str | None] = mapped_column(String(32))
    output_text: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(20))
    # Generation: {"mode": "generate" | "variation"}; Codex's thread id once known.
    settings_json: Mapped[str | None] = mapped_column(Text)
    provider_request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))


class Batch(Base):
    """Several engine runs started together (Phase 5.5). Its items are engine jobs.

    status records the user's intent: running, paused (by the user, a plan limit or a
    restart) or cancelled. Progress is derived from the items, never stored twice.
    """

    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    engine: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    pause_kind: Mapped[str | None] = mapped_column(String(30))
    pause_details: Mapped[str | None] = mapped_column(Text)
    # Generation: {"count": images per scene, "mode": "generate" | "variation"}.
    settings_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class SubjectMapping(Base):
    """What happens to one subject of a scene. Subjects without a row are unresolved."""

    __tablename__ = "subject_mappings"
    __table_args__ = (UniqueConstraint("scene_id", "subject_label"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    subject_label: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"), index=True)
    # Ordered reference photo ids; the order decides the attached image numbers.
    reference_ids: Mapped[str] = mapped_column(Text)
    references_auto: Mapped[bool] = mapped_column(Boolean)
    # Subjects (labels and boxes) the user confirmed this assignment against.
    subjects_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))


class Approval(Base):
    """Immutable approval snapshot; only the invalidation fields are ever written later."""

    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[str] = mapped_column(String(40))
    invalidated_at: Mapped[str | None] = mapped_column(String(40))
    invalidated_reason: Mapped[str | None] = mapped_column(Text)


class GenerationResult(Base):
    """One generated or imported image. Never overwritten; tied to the approval it came from."""

    __tablename__ = "generation_results"
    __table_args__ = (UniqueConstraint("scene_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), index=True)
    # The generation run or the manual export package it belongs to, if any.
    job_id: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    # Imports: what the user says made it (for example "ChatGPT Images").
    note: Mapped[str] = mapped_column(Text, default="")
    original_path: Mapped[str] = mapped_column(String(100))
    thumbnail_path: Mapped[str] = mapped_column(String(100))
    media_type: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str | None] = mapped_column(String(80))
    # Found in the run's own output folder after an interrupted, cancelled or failed run.
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


class QualityCheck(Base):
    """A user-started identity and composition check of one result (Phase 6B, D023).

    A model's opinion, never a measurement: scores 1-5 per aspect and per subject (0 means
    "could not judge"), stored as validated JSON next to the engine that produced it.
    """

    __tablename__ = "quality_checks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    result_id: Mapped[str] = mapped_column(ForeignKey("generation_results.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32))
    engine: Mapped[str] = mapped_column(String(20))
    engine_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class GenerationPreset(Base):
    """Reusable settings: scene changes and negative additions for the prompt, and how many
    images one click makes (Phase 6B). Applying a preset only fills fields; prompts are
    still saved and approved by the user.
    """

    __tablename__ = "generation_presets"
    __table_args__ = (CheckConstraint("images BETWEEN 1 AND 10"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    scene_changes: Mapped[str] = mapped_column(Text, default="")
    negative_additions: Mapped[str] = mapped_column(Text, default="")
    images: Mapped[int] = mapped_column(Integer, default=1)
    # individual, couple, family, friends or other (built-in presets live in code).
    category: Mapped[str] = mapped_column(String(20), default="other")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
