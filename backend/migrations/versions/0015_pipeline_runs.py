"""Run everything: one auto-pipeline run per row (Phase 7C-2, D037)."""

import sqlalchemy as sa
from alembic import op

revision = "0015_pipeline_runs"
down_revision = "0014_import_character"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: a new table; nothing is rebuilt.
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("scene_set_id", sa.String(32), nullable=False, index=True),
        # running, paused (a restart), waiting (stopped before generating), cancelled, finished
        sa.Column("status", sa.String(20), nullable=False),
        # analysing or generating
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("outcome_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("pause_details", sa.Text()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
