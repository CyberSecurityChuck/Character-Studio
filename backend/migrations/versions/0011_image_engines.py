"""Allow the API image engines and store their size and quality (Phase 6C-1, D025)."""

import sqlalchemy as sa
from alembic import op

revision = "0011_image_engines"
down_revision = "0010_model_lists"
branch_labels = None
depends_on = None

ANALYSIS_ENGINES = (
    "'claude_cli', 'codex_cli', 'manual', 'gemini_api', 'anthropic_api', 'openai_api'"
)
GENERATION_ENGINES = "'codex_cli', 'manual', 'gemini_api', 'openai_api'"
RESULT_SOURCES = "'codex_cli', 'manual_import', 'gemini_api', 'openai_api'"


def upgrade():
    # SQLite cannot change a CHECK constraint in place, so both tables are rebuilt with the
    # same rows (references are verified by backend.persistence before commit).
    with op.batch_alter_table("engine_settings") as batch:
        batch.add_column(
            sa.Column("image_options_json", sa.Text(), nullable=False, server_default="{}")
        )
    with op.batch_alter_table(
        "engine_settings",
        recreate="always",
        table_args=(
            sa.CheckConstraint("id = 1", name="singleton_engine_settings"),
            sa.CheckConstraint(f"analysis_engine IN ({ANALYSIS_ENGINES})"),
            sa.CheckConstraint(f"generation_engine IN ({GENERATION_ENGINES})"),
            sa.CheckConstraint("api_timeout BETWEEN 30 AND 1800"),
        ),
    ):
        pass
    with op.batch_alter_table(
        "generation_results",
        recreate="always",
        table_args=(
            sa.UniqueConstraint("scene_id", "version"),
            sa.CheckConstraint(f"source IN ({RESULT_SOURCES})"),
            sa.CheckConstraint("mode IN ('generate', 'variation', 'import')"),
        ),
    ):
        pass
    # Presets may choose the image size and quality for the API image engines.
    with op.batch_alter_table("generation_presets") as batch:
        batch.add_column(sa.Column("image_size", sa.String(4)))
        batch.add_column(sa.Column("image_quality", sa.String(10)))


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
