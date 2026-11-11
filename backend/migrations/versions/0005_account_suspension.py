"""Add administrator-controlled account suspension."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0005_account_suspension"
down_revision="0004_account_security"
branch_labels=None
depends_on=None

def upgrade():
    columns={c["name"] for c in inspect(op.get_bind()).get_columns("users")}
    if "active" not in columns:
        op.add_column("users",sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))

def downgrade():
    columns={c["name"] for c in inspect(op.get_bind()).get_columns("users")}
    if "active" in columns:op.drop_column("users","active")

