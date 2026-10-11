"""Add quality checks of results and saved generation presets (Phase 6B)."""

import sqlalchemy as sa
from alembic import op

revision = "0009_quality"
down_revision = "0008_api_engines"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: two new tables.
    op.create_table(
        "quality_checks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column(
            "result_id", sa.String(32), sa.ForeignKey("generation_results.id"), nullable=False
        ),
        sa.Column("job_id", sa.String(32)),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("engine_version", sa.String(80)),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_quality_checks_scene_id", "quality_checks", ["scene_id"])
    op.create_index("ix_quality_checks_result_id", "quality_checks", ["result_id"])
    op.create_table(
        "generation_presets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("scene_changes", sa.Text(), nullable=False),
        sa.Column("negative_additions", sa.Text(), nullable=False),
        sa.Column("images", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("images BETWEEN 1 AND 10"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
