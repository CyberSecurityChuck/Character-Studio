"""Create persistent local studio preferences.

Revision ID: 0001_foundation
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "studio_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("studio_name", sa.String(60), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="singleton_preferences"),
    )
    op.bulk_insert(table, [{"id": 1, "studio_name": "My studio", "revision": 1}])


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
