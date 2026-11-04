"""Scene sets, perceptual fingerprints and approval modes (Phase 7, D031)."""

import sqlalchemy as sa
from alembic import op

revision = "0013_scene_sets"
down_revision = "0012_region_edits"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: one new table and three nullable or defaulted columns; nothing rebuilt.
    op.create_table(
        "scene_sets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    # One set per scene; deleting a set clears this link in code and keeps the scenes.
    op.add_column("scenes", sa.Column("scene_set_id", sa.String(32)))
    op.create_index("ix_scenes_scene_set_id", "scenes", ["scene_set_id"])
    # 64-bit difference hash as 16 hex digits; filled when a duplicate check first needs it.
    op.add_column("scenes", sa.Column("perceptual_hash", sa.String(16)))
    # How the approval was given: single, bulk or auto (D030). Earlier approvals were single.
    op.add_column(
        "approvals",
        sa.Column("approval_mode", sa.String(10), nullable=False, server_default="single"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
