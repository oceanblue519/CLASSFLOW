"""Add activity classification and private class messages."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_activities_messages"
down_revision = "0005_account_suspension"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    assignment_columns = {c["name"] for c in inspector.get_columns("assignments")}
    if "kind" not in assignment_columns:
        op.add_column("assignments", sa.Column("kind", sa.String(24), nullable=False, server_default="assignment"))
    if "messages" not in inspector.get_table_names():
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_messages_class_id", "messages", ["class_id"])
        op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
        op.create_index("ix_messages_recipient_id", "messages", ["recipient_id"])

def downgrade():
    bind = op.get_bind()
    if "messages" in inspect(bind).get_table_names():
        op.drop_table("messages")
    if "kind" in {c["name"] for c in inspect(bind).get_columns("assignments")}:
        op.drop_column("assignments", "kind")
