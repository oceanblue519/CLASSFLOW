"""Add verification and password-reset tokens plus session versioning."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0004_account_security"
down_revision="0003_submission_files"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind();inspector=inspect(bind)
    user_columns={c["name"] for c in inspector.get_columns("users")}
    if "email_verified" not in user_columns:
        op.add_column("users",sa.Column("email_verified",sa.Boolean(),nullable=False,server_default=sa.true()))
    if "session_version" not in user_columns:
        op.add_column("users",sa.Column("session_version",sa.Integer(),nullable=False,server_default="0"))
    if "auth_tokens" not in inspector.get_table_names():
        op.create_table("auth_tokens",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
            sa.Column("purpose",sa.String(24),nullable=False),
            sa.Column("token_hash",sa.String(64),nullable=False,unique=True),
            sa.Column("expires",sa.DateTime(),nullable=False),
            sa.Column("used",sa.Boolean(),nullable=False,server_default=sa.false()))
        op.create_index("ix_auth_tokens_user_id","auth_tokens",["user_id"])

def downgrade():
    bind=op.get_bind();inspector=inspect(bind)
    if "auth_tokens" in inspector.get_table_names():op.drop_table("auth_tokens")
    columns={c["name"] for c in inspect(bind).get_columns("users")}
    for name in ("session_version","email_verified"):
        if name in columns:op.drop_column("users",name)

