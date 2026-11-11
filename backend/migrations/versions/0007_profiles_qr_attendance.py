"""Add profile pictures and short-lived QR attendance sessions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0007_profiles_qr_attendance"
down_revision = "0006_activities_messages"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    users = {column["name"] for column in inspector.get_columns("users")}
    if "avatar_name" not in users:
        op.add_column("users", sa.Column("avatar_name", sa.String(80), nullable=True))
    tables = set(inspector.get_table_names())
    if "attendance_sessions" not in tables:
        op.create_table(
            "attendance_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires", sa.DateTime(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_attendance_sessions_class_id", "attendance_sessions", ["class_id"])
    attendance = {column["name"] for column in inspect(bind).get_columns("attendance")}
    if "session_id" not in attendance:
        with op.batch_alter_table("attendance") as batch:
            batch.add_column(sa.Column("session_id", sa.Integer(), sa.ForeignKey("attendance_sessions.id", ondelete="SET NULL"), nullable=True))
    indexes = {index["name"] for index in inspect(bind).get_indexes("attendance")}
    if "uq_attendance_session_student" not in indexes:
        op.create_index("uq_attendance_session_student", "attendance", ["session_id", "student_id"], unique=True)

def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "uq_attendance_session_student" in {index["name"] for index in inspector.get_indexes("attendance")}:
        op.drop_index("uq_attendance_session_student", table_name="attendance")
    if "session_id" in {column["name"] for column in inspector.get_columns("attendance")}:
        op.drop_column("attendance", "session_id")
    if "attendance_sessions" in inspector.get_table_names():
        op.drop_table("attendance_sessions")
    if "avatar_name" in {column["name"] for column in inspector.get_columns("users")}:
        op.drop_column("users", "avatar_name")
