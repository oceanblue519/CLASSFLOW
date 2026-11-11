"""Add native virtual classrooms, join records, and WebRTC signaling."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0009_native_virtual_classroom"
down_revision = "0008_class_enrollment"
branch_labels = None
depends_on = None

def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "virtual_rooms" not in tables:
        op.create_table(
            "virtual_rooms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("ended", sa.DateTime(), nullable=True),
        )
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("virtual_rooms")}
    if "ix_virtual_rooms_class_id" not in indexes:
        op.create_index("ix_virtual_rooms_class_id", "virtual_rooms", ["class_id"])
    if "ix_virtual_rooms_active" not in indexes:
        op.create_index("ix_virtual_rooms_active", "virtual_rooms", ["active"])
    if "virtual_presence" not in tables:
        op.create_table(
            "virtual_presence",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("room_id", sa.Integer(), sa.ForeignKey("virtual_rooms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("last_seen", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("left_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        )
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("virtual_presence")}
    if "ix_virtual_presence_room_id" not in indexes:
        op.create_index("ix_virtual_presence_room_id", "virtual_presence", ["room_id"])
    if "ix_virtual_presence_user_id" not in indexes:
        op.create_index("ix_virtual_presence_user_id", "virtual_presence", ["user_id"])
    if "virtual_signals" not in tables:
        op.create_table(
            "virtual_signals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("room_id", sa.Integer(), sa.ForeignKey("virtual_rooms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_presence_id", sa.Integer(), sa.ForeignKey("virtual_presence.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recipient_presence_id", sa.Integer(), sa.ForeignKey("virtual_presence.id", ondelete="CASCADE"), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("virtual_signals")}
    if "ix_virtual_signals_room_id" not in indexes:
        op.create_index("ix_virtual_signals_room_id", "virtual_signals", ["room_id"])
    if "ix_virtual_signals_sender_presence_id" not in indexes:
        op.create_index("ix_virtual_signals_sender_presence_id", "virtual_signals", ["sender_presence_id"])
    if "ix_virtual_signals_recipient_presence_id" not in indexes:
        op.create_index("ix_virtual_signals_recipient_presence_id", "virtual_signals", ["recipient_presence_id"])

def downgrade():
    op.drop_table("virtual_signals")
    op.drop_table("virtual_presence")
    op.drop_table("virtual_rooms")
