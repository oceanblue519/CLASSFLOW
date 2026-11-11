"""Add encrypted Google credentials and Google Meet attendance metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_google_meet"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    inspector=inspect(bind)
    columns={c["name"] for c in inspector.get_columns("attendance")}
    if "source" not in columns:
        op.add_column("attendance",sa.Column("source",sa.String(30),nullable=False,server_default="teacher"))
    if "meeting_id" not in columns:
        op.add_column("attendance",sa.Column("meeting_id",sa.Integer(),nullable=True))
    if "joined_at" not in columns:
        op.add_column("attendance",sa.Column("joined_at",sa.DateTime(),nullable=True))
    if "left_at" not in columns:
        op.add_column("attendance",sa.Column("left_at",sa.DateTime(),nullable=True))
    if "duration_seconds" not in columns:
        op.add_column("attendance",sa.Column("duration_seconds",sa.Integer(),nullable=True))
    inspector=inspect(bind)
    tables=set(inspector.get_table_names())
    if "google_credentials" not in tables:
        op.create_table("google_credentials",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False,unique=True),
            sa.Column("token_ciphertext",sa.Text(),nullable=False),
            sa.Column("updated",sa.DateTime(),nullable=False))
    if "meetings" not in tables:
        op.create_table("meetings",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("class_id",sa.Integer(),sa.ForeignKey("classes.id",ondelete="CASCADE"),nullable=False),
            sa.Column("creator_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),
            sa.Column("title",sa.String(180),nullable=False),
            sa.Column("starts",sa.DateTime(),nullable=False),
            sa.Column("ends",sa.DateTime(),nullable=False),
            sa.Column("meet_url",sa.String(500),nullable=False),
            sa.Column("meeting_code",sa.String(40),nullable=False),
            sa.Column("calendar_event_id",sa.String(200),nullable=False),
            sa.Column("created",sa.DateTime(),nullable=False))
        op.create_index("ix_meetings_class_id","meetings",["class_id"])
    if "meeting_participants" not in tables:
        op.create_table("meeting_participants",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("meeting_id",sa.Integer(),sa.ForeignKey("meetings.id",ondelete="CASCADE"),nullable=False),
            sa.Column("participant_ref",sa.String(500),nullable=False),
            sa.Column("display_name",sa.String(200),nullable=False),
            sa.Column("student_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL"),nullable=True),
            sa.Column("joined_at",sa.DateTime(),nullable=True),
            sa.Column("left_at",sa.DateTime(),nullable=True),
            sa.Column("duration_seconds",sa.Integer(),nullable=False,server_default="0"),
            sa.Column("confirmed",sa.Boolean(),nullable=False,server_default=sa.false()),
            sa.UniqueConstraint("meeting_id","participant_ref"))
        op.create_index("ix_meeting_participants_meeting_id","meeting_participants",["meeting_id"])

def downgrade():
    bind=op.get_bind()
    tables=set(inspect(bind).get_table_names())
    for table in ("meeting_participants","meetings","google_credentials"):
        if table in tables:
            op.drop_table(table)
    columns={c["name"] for c in inspect(bind).get_columns("attendance")}
    for name in ("duration_seconds","left_at","joined_at","meeting_id","source"):
        if name in columns:
            op.drop_column("attendance",name)

