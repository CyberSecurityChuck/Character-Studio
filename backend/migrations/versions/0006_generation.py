"""Add generation results and generation job fields (Phase 5)."""

import sqlalchemy as sa
from alembic import op

revision = "0006_generation"
down_revision = "0005_mapping"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: two nullable job columns and one new table.
    op.add_column("engine_jobs", sa.Column("settings_json", sa.Text()))
    op.add_column("engine_jobs", sa.Column("provider_request_id", sa.String(80)))
    op.create_table(
        "generation_results",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("approval_id", sa.String(32), sa.ForeignKey("approvals.id"), nullable=False),
        sa.Column("job_id", sa.String(32)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("original_path", sa.String(100), nullable=False),
        sa.Column("thumbnail_path", sa.String(100), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(80)),
        sa.Column("recovered", sa.Boolean(), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("scene_id", "version"),
        sa.CheckConstraint("source IN ('codex_cli', 'manual_import')"),
        sa.CheckConstraint("mode IN ('generate', 'variation', 'import')"),
    )
    op.create_index("ix_generation_results_scene_id", "generation_results", ["scene_id"])
    op.create_index("ix_generation_results_approval_id", "generation_results", ["approval_id"])


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
