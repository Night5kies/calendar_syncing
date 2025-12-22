"""phase one tables

Revision ID: 7f2e3b9c1a0d
Revises: 
Create Date: 2025-12-21 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7f2e3b9c1a0d"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "meeting_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizer_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meeting_requests_organizer_id", "meeting_requests", ["organizer_id"], unique=False)
    op.create_index("ix_meeting_requests_status", "meeting_requests", ["status"], unique=False)

    op.create_table(
        "participants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'attendee'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'invited'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_request_id"],
            ["meeting_requests.id"],
            name="fk_participants_meeting_request_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_participants_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_request_id", "email", name="uq_participants_request_email"),
    )
    op.create_index("ix_participants_meeting_request_id", "participants", ["meeting_request_id"], unique=False)
    op.create_index("ix_participants_user_id", "participants", ["user_id"], unique=False)
    op.create_index("ix_participants_email", "participants", ["email"], unique=False)
    op.create_index("ix_participants_status", "participants", ["status"], unique=False)

    op.create_table(
        "share_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_request_id"],
            ["meeting_requests.id"],
            name="fk_share_links_meeting_request_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_share_links_participant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_share_links_meeting_request_id", "share_links", ["meeting_request_id"], unique=False)
    op.create_index("ix_share_links_participant_id", "share_links", ["participant_id"], unique=False)
    op.create_index("ix_share_links_token", "share_links", ["token"], unique=True)

    op.create_table(
        "availability_responses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=32), server_default=sa.text("'link'"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_availability_responses_participant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_responses_participant_id",
        "availability_responses",
        ["participant_id"],
        unique=False,
    )

    op.create_table(
        "scheduled_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_request_id"],
            ["meeting_requests.id"],
            name="fk_scheduled_events_meeting_request_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_events_meeting_request_id", "scheduled_events", ["meeting_request_id"], unique=False)
    op.create_index("ix_scheduled_events_status", "scheduled_events", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduled_events_status", table_name="scheduled_events")
    op.drop_index("ix_scheduled_events_meeting_request_id", table_name="scheduled_events")
    op.drop_table("scheduled_events")
    op.drop_index("ix_availability_responses_participant_id", table_name="availability_responses")
    op.drop_table("availability_responses")
    op.drop_index("ix_share_links_token", table_name="share_links")
    op.drop_index("ix_share_links_participant_id", table_name="share_links")
    op.drop_index("ix_share_links_meeting_request_id", table_name="share_links")
    op.drop_table("share_links")
    op.drop_index("ix_participants_status", table_name="participants")
    op.drop_index("ix_participants_email", table_name="participants")
    op.drop_index("ix_participants_user_id", table_name="participants")
    op.drop_index("ix_participants_meeting_request_id", table_name="participants")
    op.drop_table("participants")
    op.drop_index("ix_meeting_requests_status", table_name="meeting_requests")
    op.drop_index("ix_meeting_requests_organizer_id", table_name="meeting_requests")
    op.drop_table("meeting_requests")
    op.drop_table("profiles")
