"""Allow teachers to archive ended virtual classroom sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0010_virtual_room_archive"
down_revision = "0009_native_virtual_classroom"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "virtual_rooms",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_virtual_rooms_archived", "virtual_rooms", ["archived"])


def downgrade():
    op.drop_index("ix_virtual_rooms_archived", table_name="virtual_rooms")
    op.drop_column("virtual_rooms", "archived")