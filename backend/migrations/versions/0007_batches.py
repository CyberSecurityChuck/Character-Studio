"""Add batches and the position of each batch item (Phase 5.5)."""

import sqlalchemy as sa
from alembic import op

revision = "0007_batches"
down_revision = "0006_generation"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: one new table and one nullable job column.
    op.create_table(
        "batches",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pause_kind", sa.String(30)),
        sa.Column("pause_details", sa.Text()),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("kind IN ('analysis', 'generation')"),
        sa.CheckConstraint("status IN ('running', 'paused', 'cancelled')"),
    )
    op.add_column("engine_jobs", sa.Column("batch_position", sa.Integer()))
    op.create_index("ix_engine_jobs_batch_id", "engine_jobs", ["batch_id"])


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
