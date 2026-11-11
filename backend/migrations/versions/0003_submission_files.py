"""Add secure assignment upload metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0003_submission_files"
down_revision="0002_google_meet"
branch_labels=None
depends_on=None

def upgrade():
    columns={c["name"] for c in inspect(op.get_bind()).get_columns("submissions")}
    if "file_name" not in columns:
        op.add_column("submissions",sa.Column("file_name",sa.String(240),nullable=False,server_default=""))
    if "stored_file" not in columns:
        op.add_column("submissions",sa.Column("stored_file",sa.String(80),nullable=True))

def downgrade():
    columns={c["name"] for c in inspect(op.get_bind()).get_columns("submissions")}
    if "stored_file" in columns:op.drop_column("submissions","stored_file")
    if "file_name" in columns:op.drop_column("submissions","file_name")

