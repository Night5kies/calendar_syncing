"""request status, responses, and availability

Revision ID: 3b5f2c9a1f47
Revises: 2c1b9f3a7d8e
Create Date: 2026-01-06 19:05:00.000000

Status migration note: any unrecognized meeting_requests.status values are coerced to 'sent'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3b5f2c9a1f47"
down_revision: Union[str, None] = "2c1b9f3a7d8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE meeting_requests
        SET status = CASE
            WHEN status IS NULL THEN 'draft'
            WHEN status IN ('sent', 'confirmed', 'canceled') THEN status
            ELSE 'sent'
        END
        """
    )
    op.alter_column(
        "meeting_requests",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        server_default=sa.text("'draft'"),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_meeting_requests_status",
        "meeting_requests",
        "status IN ('draft', 'sent', 'collecting', 'needs_organizer_confirm', 'confirmed', 'canceled', 'expired')",
    )

    op.drop_column("proposals", "end_at")

    op.add_column("participants", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("participants", sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE participants
        SET responded_at = COALESCE(responded_at, created_at)
        WHERE status = 'responded' AND responded_at IS NULL
        """
    )

    op.rename_table("proposal_selections", "proposal_responses")
    op.execute(
        "ALTER INDEX ix_proposal_selections_meeting_request_id RENAME TO ix_proposal_responses_meeting_request_id"
    )
    op.execute(
        "ALTER INDEX ix_proposal_selections_participant_id RENAME TO ix_proposal_responses_participant_id"
    )
    op.execute("ALTER INDEX ix_proposal_selections_proposal_id RENAME TO ix_proposal_responses_proposal_id")
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT uq_proposal_selections_request_participant TO uq_proposal_responses_request_participant"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_selections_meeting_request_id TO fk_proposal_responses_meeting_request_id"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_selections_participant_id TO fk_proposal_responses_participant_id"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_selections_proposal_id TO fk_proposal_responses_proposal_id"
    )
    op.alter_column(
        "proposal_responses",
        "proposal_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.add_column(
        "proposal_responses",
        sa.Column("choice", sa.String(length=16), server_default=sa.text("'picked'"), nullable=False),
    )
    op.add_column("proposal_responses", sa.Column("comment", sa.Text(), nullable=True))
    op.execute("UPDATE proposal_responses SET choice = 'picked' WHERE choice IS NULL")
    op.create_check_constraint(
        "ck_proposal_responses_choice",
        "proposal_responses",
        "choice IN ('picked', 'declined', 'maybe')",
    )
    op.create_check_constraint(
        "ck_proposal_responses_picked_requires_proposal",
        "proposal_responses",
        "(choice != 'picked') OR (proposal_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_proposal_responses_declined_requires_null",
        "proposal_responses",
        "(choice != 'declined') OR (proposal_id IS NULL)",
    )

    op.add_column("scheduled_events", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("scheduled_events", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("scheduled_events", sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduled_events", sa.Column("duration_min", sa.Integer(), nullable=True))
    op.add_column("scheduled_events", sa.Column("event_type", sa.String(length=64), nullable=True))
    op.add_column("scheduled_events", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column("scheduled_events", sa.Column("video_link", sa.String(length=255), nullable=True))
    op.add_column("scheduled_events", sa.Column("notes", sa.String(length=1000), nullable=True))
    op.execute(
        """
        UPDATE scheduled_events
        SET title = mr.title,
            timezone = mr.timezone,
            start_at = p.start_at,
            duration_min = mr.duration_min,
            event_type = mr.event_type,
            location = mr.location,
            video_link = mr.video_link,
            notes = mr.notes
        FROM meeting_requests mr, proposals p
        WHERE scheduled_events.meeting_request_id = mr.id
          AND scheduled_events.proposal_id = p.id
        """
    )
    op.alter_column(
        "scheduled_events",
        "title",
        existing_type=sa.String(length=200),
        nullable=False,
    )
    op.alter_column(
        "scheduled_events",
        "timezone",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "scheduled_events",
        "start_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "scheduled_events",
        "duration_min",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_scheduled_events_meeting_request_id",
        "scheduled_events",
        ["meeting_request_id"],
    )

    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_calendar_connections_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_account_id",
            name="uq_calendar_connections_user_provider_account",
        ),
    )
    op.create_index(
        "ix_calendar_connections_user_id",
        "calendar_connections",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "availability_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("weekly_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_availability_rules_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_availability_rules_user_id", "availability_rules", ["user_id"], unique=False)

    op.create_table(
        "availability_blocks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_availability_blocks_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_availability_blocks_user_id", "availability_blocks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_availability_blocks_user_id", table_name="availability_blocks")
    op.drop_table("availability_blocks")
    op.drop_index("ix_availability_rules_user_id", table_name="availability_rules")
    op.drop_table("availability_rules")
    op.drop_index("ix_calendar_connections_user_id", table_name="calendar_connections")
    op.drop_table("calendar_connections")

    op.drop_constraint("uq_scheduled_events_meeting_request_id", "scheduled_events", type_="unique")
    op.drop_column("scheduled_events", "notes")
    op.drop_column("scheduled_events", "video_link")
    op.drop_column("scheduled_events", "location")
    op.drop_column("scheduled_events", "event_type")
    op.drop_column("scheduled_events", "duration_min")
    op.drop_column("scheduled_events", "start_at")
    op.drop_column("scheduled_events", "timezone")
    op.drop_column("scheduled_events", "title")

    op.drop_constraint("ck_proposal_responses_declined_requires_null", "proposal_responses", type_="check")
    op.drop_constraint("ck_proposal_responses_picked_requires_proposal", "proposal_responses", type_="check")
    op.drop_constraint("ck_proposal_responses_choice", "proposal_responses", type_="check")
    op.drop_column("proposal_responses", "comment")
    op.drop_column("proposal_responses", "choice")
    op.alter_column(
        "proposal_responses",
        "proposal_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_responses_proposal_id TO fk_proposal_selections_proposal_id"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_responses_participant_id TO fk_proposal_selections_participant_id"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT fk_proposal_responses_meeting_request_id TO fk_proposal_selections_meeting_request_id"
    )
    op.execute(
        "ALTER TABLE proposal_responses RENAME CONSTRAINT uq_proposal_responses_request_participant TO uq_proposal_selections_request_participant"
    )
    op.execute("ALTER INDEX ix_proposal_responses_proposal_id RENAME TO ix_proposal_selections_proposal_id")
    op.execute("ALTER INDEX ix_proposal_responses_participant_id RENAME TO ix_proposal_selections_participant_id")
    op.execute(
        "ALTER INDEX ix_proposal_responses_meeting_request_id RENAME TO ix_proposal_selections_meeting_request_id"
    )
    op.rename_table("proposal_responses", "proposal_selections")

    op.drop_column("participants", "last_viewed_at")
    op.drop_column("participants", "responded_at")

    op.drop_constraint("ck_meeting_requests_status", "meeting_requests", type_="check")
    op.execute(
        """
        UPDATE meeting_requests
        SET status = CASE
            WHEN status IN ('sent', 'confirmed', 'canceled') THEN status
            ELSE 'sent'
        END
        """
    )
    op.alter_column(
        "meeting_requests",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=20),
        server_default=sa.text("'sent'"),
        nullable=False,
    )

    op.add_column("proposals", sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE proposals p
        SET end_at = p.start_at + (mr.duration_min || ' minutes')::interval
        FROM meeting_requests mr
        WHERE mr.id = p.meeting_request_id AND p.end_at IS NULL
        """
    )
    op.alter_column(
        "proposals",
        "end_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
