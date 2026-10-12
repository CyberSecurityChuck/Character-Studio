"""Region edits: results that edit another result (Phase 6C-2, D027)."""

import sqlalchemy as sa
from alembic import op

revision = "0012_region_edits"
down_revision = "0011_image_engines"
branch_labels = None
depends_on = None

RESULT_SOURCES = "'codex_cli', 'manual_import', 'gemini_api', 'openai_api', 'bfl_api'"


def upgrade():
    # SQLite cannot change a CHECK constraint in place, so the table is rebuilt with the
    # same rows (references are verified by backend.persistence before commit).
    with op.batch_alter_table("generation_results") as batch:
        batch.add_column(sa.Column("parent_result_id", sa.String(32)))
        batch.add_column(sa.Column("edit_json", sa.Text()))
    with op.batch_alter_table(
        "generation_results",
        recreate="always",
        table_args=(
            sa.UniqueConstraint("scene_id", "version"),
            sa.CheckConstraint(f"source IN ({RESULT_SOURCES})"),
            sa.CheckConstraint("mode IN ('generate', 'variation', 'import', 'edit')"),
        ),
    ):
        pass


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
