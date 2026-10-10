"""Add subject mappings, approval snapshots and prompt polishing fields (Phase 4)."""

import sqlalchemy as sa
from alembic import op

revision = "0005_mapping"
down_revision = "0004_scenes"
branch_labels = None
depends_on = None


def upgrade():
    # Additive, nullable columns only; existing rows stay valid.
    op.add_column("reference_photos", sa.Column("content_hash", sa.String(64)))
    op.add_column("scenes", sa.Column("mapping_group_id", sa.String(32)))
    op.add_column("prompt_versions", sa.Column("mapping_hash", sa.String(64)))
    op.add_column("engine_jobs", sa.Column("input_id", sa.String(32)))
    op.add_column("engine_jobs", sa.Column("output_text", sa.Text()))
    op.add_column("engine_jobs", sa.Column("decision", sa.String(20)))
    op.create_table(
        "subject_mappings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("subject_label", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id")),
        sa.Column("reference_ids", sa.Text(), nullable=False),
        sa.Column("references_auto", sa.Boolean(), nullable=False),
        sa.Column("subjects_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("scene_id", "subject_label"),
        sa.CheckConstraint("action IN ('replace', 'keep', 'unresolved')"),
        sa.CheckConstraint("action = 'replace' OR character_id IS NULL"),
    )
    op.create_index("ix_subject_mappings_scene_id", "subject_mappings", ["scene_id"])
    op.create_index("ix_subject_mappings_character_id", "subject_mappings", ["character_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.String(40), nullable=False),
        sa.Column("invalidated_at", sa.String(40)),
        sa.Column("invalidated_reason", sa.Text()),
    )
    op.create_index("ix_approvals_scene_id", "approvals", ["scene_id"])


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
