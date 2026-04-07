"""request reminders

Revision ID: a6d9c3e4f201
Revises: 9c4d1a7b2e91
Create Date: 2026-03-18 17:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a6d9c3e4f201"
down_revision: Union[str, None] = "9c4d1a7b2e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meeting_requests", sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "meeting_requests",
        sa.Column("reminders_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "meeting_requests",
        sa.Column("reminder_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("meeting_requests", sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "reminder_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("target", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_request_id"], ["meeting_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminder_logs_meeting_request_id", "reminder_logs", ["meeting_request_id"], unique=False)
    op.create_index("ix_reminder_logs_participant_id", "reminder_logs", ["participant_id"], unique=False)
    op.create_index("ix_reminder_logs_reason", "reminder_logs", ["reason"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminder_logs_reason", table_name="reminder_logs")
    op.drop_index("ix_reminder_logs_participant_id", table_name="reminder_logs")
    op.drop_index("ix_reminder_logs_meeting_request_id", table_name="reminder_logs")
    op.drop_table("reminder_logs")

    op.drop_column("meeting_requests", "last_reminded_at")
    op.drop_column("meeting_requests", "reminder_count")
    op.drop_column("meeting_requests", "reminders_enabled")
    op.drop_column("meeting_requests", "response_deadline")
