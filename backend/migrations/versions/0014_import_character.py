"""A character chosen at import and the number of characters a fill rule meant (Phase 7B, D035)."""

import sqlalchemy as sa
from alembic import op

revision = "0014_import_character"
down_revision = "0013_scene_sets"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only: two nullable columns; nothing is rebuilt.
    # The character the user picked for this image at import, applied once the analysis has
    # found the people and then cleared.
    op.add_column("scenes", sa.Column("import_character_id", sa.String(32)))
    # How many characters an import choice or a fill rule meant to place. Compared with the
    # people found to label mismatches; cleared when the user assigns by hand.
    op.add_column("scenes", sa.Column("intended_characters", sa.Integer()))


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
