"""Saved model lists per engine and preset categories (Phase 6A/6B review fixes)."""

import sqlalchemy as sa
from alembic import op

revision = "0010_model_lists"
down_revision = "0009_quality"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: two columns with defaults.
    with op.batch_alter_table("engine_settings") as batch:
        batch.add_column(
            sa.Column("model_lists_json", sa.Text(), nullable=False, server_default="{}")
        )
    with op.batch_alter_table("generation_presets") as batch:
        batch.add_column(
            sa.Column("category", sa.String(20), nullable=False, server_default="other")
        )


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
