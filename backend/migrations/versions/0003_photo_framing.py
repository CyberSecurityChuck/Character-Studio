"""Add avatar framing to reference photos; existing photos keep the default framing."""

import sqlalchemy as sa
from alembic import op

revision = "0003_photo_framing"
down_revision = "0002_library"
branch_labels = None
depends_on = None


def upgrade():
    for name, default in (("frame_x", "0.5"), ("frame_y", "0.3"), ("frame_zoom", "1.0")):
        op.add_column(
            "reference_photos",
            sa.Column(name, sa.Float(), nullable=False, server_default=sa.text(default)),
        )


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled; restore a verified backup instead.")
