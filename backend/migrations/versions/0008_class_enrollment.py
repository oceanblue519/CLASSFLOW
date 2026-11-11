"""Add public enrollment controls to classes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0008_class_enrollment"
down_revision = "0007_profiles_qr_attendance"
branch_labels = None
depends_on = None

def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("classes")}
    if "enrollment_open" not in columns:
        op.add_column("classes", sa.Column("enrollment_open", sa.Boolean(), nullable=False, server_default=sa.true()))

def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("classes")}
    if "enrollment_open" in columns:
        op.drop_column("classes", "enrollment_open")
