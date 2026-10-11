"""Allow the API analysis engines and store their models and time limit (Phase 6A)."""

import sqlalchemy as sa
from alembic import op

revision = "0008_api_engines"
down_revision = "0007_batches"
branch_labels = None
depends_on = None

ANALYSIS_ENGINES = (
    "'claude_cli', 'codex_cli', 'manual', 'gemini_api', 'anthropic_api', 'openai_api'"
)
ANALYSIS_SOURCES = (
    "'claude_cli', 'codex_cli', 'manual_import', 'user_edit', "
    "'gemini_api', 'anthropic_api', 'openai_api'"
)


def upgrade():
    # SQLite cannot change a CHECK constraint in place, so both tables are rebuilt with the
    # same rows (references are verified by backend.persistence before commit).
    with op.batch_alter_table("engine_settings") as batch:
        batch.add_column(
            sa.Column("api_timeout", sa.Integer(), nullable=False, server_default="180")
        )
        batch.add_column(
            sa.Column("api_models_json", sa.Text(), nullable=False, server_default="{}")
        )
    with op.batch_alter_table(
        "engine_settings",
        recreate="always",
        table_args=(
            sa.CheckConstraint("id = 1", name="singleton_engine_settings"),
            sa.CheckConstraint(f"analysis_engine IN ({ANALYSIS_ENGINES})"),
            sa.CheckConstraint("generation_engine IN ('codex_cli', 'manual')"),
            sa.CheckConstraint("api_timeout BETWEEN 30 AND 1800"),
        ),
    ):
        pass
    with op.batch_alter_table(
        "scene_analyses",
        recreate="always",
        table_args=(
            sa.UniqueConstraint("scene_id", "version"),
            sa.CheckConstraint(f"source IN ({ANALYSIS_SOURCES})"),
        ),
    ):
        pass


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
