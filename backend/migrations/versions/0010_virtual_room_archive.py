"""Allow teachers to archive ended virtual classroom sessions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0010_virtual_room_archive"
down_revision = "0009_native_virtual_classroom"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("virtual_rooms")}
    if "archived" not in columns:
        op.add_column(
            "virtual_rooms",
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("virtual_rooms")}
    if "ix_virtual_rooms_archived" not in indexes:
        op.create_index("ix_virtual_rooms_archived", "virtual_rooms", ["archived"])


def downgrade():
    op.drop_index("ix_virtual_rooms_archived", table_name="virtual_rooms")
    op.drop_column("virtual_rooms", "archived")