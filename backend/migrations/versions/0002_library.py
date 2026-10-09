"""Add the local character library without changing existing preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0002_library"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "characters",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("age_category", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("primary_photo_id", sa.String(32)),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("age_category IN ('Adult', 'Teen', 'Child')"),
    )
    op.create_table(
        "reference_photos",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("label", sa.String(30), nullable=False),
        sa.Column("original_path", sa.String(100), nullable=False),
        sa.Column("thumbnail_path", sa.String(100), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_reference_photos_character_id", "reference_photos", ["character_id"])
    op.create_table(
        "character_groups",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "group_members",
        sa.Column(
            "group_id", sa.String(32), sa.ForeignKey("character_groups.id"), primary_key=True
        ),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id"), primary_key=True),
    )
    op.create_table("pending_file_deletions", sa.Column("path", sa.String(100), primary_key=True))


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
