"""notification_events

Revision ID: f1b4c7d9a623
Revises: e0a3b8d5c812
Create Date: 2026-05-26 09:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1b4c7d9a623"
down_revision: Union[str, None] = "e0a3b8d5c812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scheduled_event_id", sa.UUID(), nullable=True),
        sa.Column("meeting_request_id", sa.UUID(), nullable=True),
        sa.Column("participant_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("target", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'sent'"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scheduled_event_id"], ["scheduled_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_request_id"], ["meeting_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scheduled_event_id",
            "participant_id",
            "kind",
            name="uq_notification_events_event_participant_kind",
        ),
    )
    op.create_index(
        "ix_notification_events_scheduled_event_id",
        "notification_events",
        ["scheduled_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_events_meeting_request_id",
        "notification_events",
        ["meeting_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_events_participant_id",
        "notification_events",
        ["participant_id"],
        unique=False,
    )
    op.create_index("ix_notification_events_kind", "notification_events", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notification_events_kind", table_name="notification_events")
    op.drop_index("ix_notification_events_participant_id", table_name="notification_events")
    op.drop_index("ix_notification_events_meeting_request_id", table_name="notification_events")
    op.drop_index("ix_notification_events_scheduled_event_id", table_name="notification_events")
    op.drop_table("notification_events")
