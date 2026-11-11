"""Approve existing teacher accounts without requiring administrator review."""
from alembic import op
import sqlalchemy as sa

revision = "0011_teacher_self_registration"
down_revision = "0010_virtual_room_archive"
branch_labels = None
depends_on = None


def upgrade():
    users = sa.table(
        "users",
        sa.column("role", sa.String()),
        sa.column("approved", sa.Boolean()),
    )
    op.get_bind().execute(
        users.update().where(users.c.role == "teacher").values(approved=True)
    )


def downgrade():
    pass
