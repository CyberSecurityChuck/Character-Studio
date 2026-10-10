"""Add scenes, versioned analyses and prompts, engine jobs and engine settings (Phase 3)."""

import sqlalchemy as sa
from alembic import op

revision = "0004_scenes"
down_revision = "0003_photo_framing"
branch_labels = None
depends_on = None


def upgrade():
    settings = op.create_table(
        "engine_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_engine", sa.String(20), nullable=False),
        sa.Column("generation_engine", sa.String(20), nullable=False),
        sa.Column("claude_timeout", sa.Integer(), nullable=False),
        sa.Column("codex_timeout", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="singleton_engine_settings"),
        sa.CheckConstraint("analysis_engine IN ('claude_cli', 'codex_cli', 'manual')"),
        sa.CheckConstraint("generation_engine IN ('codex_cli', 'manual')"),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "analysis_engine": "claude_cli",
                "generation_engine": "codex_cli",
                "claude_timeout": 300,
                "codex_timeout": 300,
                "revision": 1,
            }
        ],
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("original_path", sa.String(100), nullable=False),
        sa.Column("thumbnail_path", sa.String(100), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("workflow_state", sa.String(30), nullable=False),
        sa.Column("duplicated_from", sa.String(32)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("last_opened_at", sa.String(40)),
    )
    op.create_table(
        "scene_analyses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("structured_analysis", sa.Text(), nullable=False),
        sa.Column("analysis_text", sa.Text(), nullable=False),
        sa.Column("confirmed_uncertainties", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("engine_version", sa.String(80)),
        sa.Column("raw_output_path", sa.String(200)),
        sa.Column("based_on_id", sa.String(32)),
        sa.Column("job_id", sa.String(32)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("scene_id", "version"),
        sa.CheckConstraint("source IN ('claude_cli', 'codex_cli', 'manual_import', 'user_edit')"),
    )
    op.create_index("ix_scene_analyses_scene_id", "scene_analyses", ["scene_id"])
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("analysis_id", sa.String(32), sa.ForeignKey("scene_analyses.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("scene_changes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("is_polished", sa.Boolean(), nullable=False),
        sa.Column("polished_from_version_id", sa.String(32)),
        sa.Column("engine_version", sa.String(80)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("scene_id", "version"),
    )
    op.create_index("ix_prompt_versions_scene_id", "prompt_versions", ["scene_id"])
    op.create_table(
        "engine_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("engine_version", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("batch_id", sa.String(32)),
        sa.Column("job_folder", sa.String(200)),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.String(30)),
        sa.Column("error_details", sa.Text()),
        sa.Column("result_id", sa.String(32)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("started_at", sa.String(40)),
        sa.Column("finished_at", sa.String(40)),
        sa.CheckConstraint(
            "status IN ('not_started', 'running', 'completed', 'failed', 'cancelled', "
            "'interrupted')"
        ),
    )
    op.create_index("ix_engine_jobs_scene_id", "engine_jobs", ["scene_id"])
    op.create_index("ix_engine_jobs_status", "engine_jobs", ["status"])


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
