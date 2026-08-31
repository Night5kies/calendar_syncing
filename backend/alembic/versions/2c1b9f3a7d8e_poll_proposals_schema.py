"""poll proposals schema

Revision ID: 2c1b9f3a7d8e
Revises: 7f2e3b9c1a0d
Create Date: 2025-12-21 21:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2c1b9f3a7d8e"
down_revision: Union[str, None] = "7f2e3b9c1a0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meeting_requests", sa.Column("group_id", sa.UUID(), nullable=True))
    op.add_column("meeting_requests", sa.Column("event_type", sa.String(length=64), nullable=True))
    op.add_column("meeting_requests", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column("meeting_requests", sa.Column("video_link", sa.String(length=255), nullable=True))
    op.add_column("meeting_requests", sa.Column("notes", sa.String(length=1000), nullable=True))
    op.create_index("ix_meeting_requests_group_id", "meeting_requests", ["group_id"], unique=False)
    op.alter_column(
        "meeting_requests",
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'sent'"),
        nullable=False,
    )
    op.drop_column("meeting_requests", "window_start")
    op.drop_column("meeting_requests", "window_end")
    op.drop_column("meeting_requests", "constraints")

    op.drop_constraint("uq_participants_request_email", "participants", type_="unique")
    op.alter_column("participants", "email", existing_type=sa.String(length=320), nullable=True)
    op.add_column("participants", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("participants", sa.Column("contact_key", sa.String(length=380), nullable=False))
    op.create_index("ix_participants_phone", "participants", ["phone"], unique=False)
    op.create_unique_constraint(
        "uq_participants_request_contact_key",
        "participants",
        ["meeting_request_id", "contact_key"],
    )

    op.drop_table("availability_responses")

    op.create_table(
        "proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_request_id"],
            ["meeting_requests.id"],
            name="fk_proposals_meeting_request_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_request_id", "rank", name="uq_proposals_request_rank"),
    )
    op.create_index("ix_proposals_meeting_request_id", "proposals", ["meeting_request_id"], unique=False)

    op.create_table(
        "proposal_selections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_request_id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_request_id"],
            ["meeting_requests.id"],
            name="fk_proposal_selections_meeting_request_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_proposal_selections_participant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name="fk_proposal_selections_proposal_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meeting_request_id",
            "participant_id",
            name="uq_proposal_selections_request_participant",
        ),
    )
    op.create_index(
        "ix_proposal_selections_meeting_request_id",
        "proposal_selections",
        ["meeting_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_proposal_selections_participant_id",
        "proposal_selections",
        ["participant_id"],
        unique=False,
    )
    op.create_index(
        "ix_proposal_selections_proposal_id",
        "proposal_selections",
        ["proposal_id"],
        unique=False,
    )

    op.add_column("scheduled_events", sa.Column("proposal_id", sa.UUID(), nullable=False))
    op.create_index("ix_scheduled_events_proposal_id", "scheduled_events", ["proposal_id"], unique=False)
    op.create_foreign_key(
        "fk_scheduled_events_proposal_id",
        "scheduled_events",
        "proposals",
        ["proposal_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "scheduled_events",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'confirmed'"),
        nullable=False,
    )
    op.drop_column("scheduled_events", "slot_start")
    op.drop_column("scheduled_events", "slot_end")
    op.drop_column("scheduled_events", "provider")
    op.drop_column("scheduled_events", "provider_event_id")


def downgrade() -> None:
    op.add_column("scheduled_events", sa.Column("provider_event_id", sa.String(length=255), nullable=True))
    op.add_column("scheduled_events", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("scheduled_events", sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False))
    op.add_column("scheduled_events", sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False))
    op.alter_column(
        "scheduled_events",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'pending'"),
        nullable=False,
    )
    op.drop_constraint("fk_scheduled_events_proposal_id", "scheduled_events", type_="foreignkey")
    op.drop_index("ix_scheduled_events_proposal_id", table_name="scheduled_events")
    op.drop_column("scheduled_events", "proposal_id")

    op.drop_index("ix_proposal_selections_proposal_id", table_name="proposal_selections")
    op.drop_index("ix_proposal_selections_participant_id", table_name="proposal_selections")
    op.drop_index("ix_proposal_selections_meeting_request_id", table_name="proposal_selections")
    op.drop_table("proposal_selections")
    op.drop_index("ix_proposals_meeting_request_id", table_name="proposals")
    op.drop_table("proposals")

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

    op.drop_constraint("uq_participants_request_contact_key", "participants", type_="unique")
    op.drop_index("ix_participants_phone", table_name="participants")
    op.drop_column("participants", "contact_key")
    op.drop_column("participants", "phone")
    op.alter_column("participants", "email", existing_type=sa.String(length=320), nullable=False)
    op.create_unique_constraint(
        "uq_participants_request_email",
        "participants",
        ["meeting_request_id", "email"],
    )

    op.add_column("meeting_requests", sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    op.add_column("meeting_requests", sa.Column("window_end", sa.DateTime(timezone=True), nullable=False))
    op.add_column("meeting_requests", sa.Column("window_start", sa.DateTime(timezone=True), nullable=False))
    op.drop_index("ix_meeting_requests_group_id", table_name="meeting_requests")
    op.drop_column("meeting_requests", "notes")
    op.drop_column("meeting_requests", "video_link")
    op.drop_column("meeting_requests", "location")
    op.drop_column("meeting_requests", "event_type")
    op.drop_column("meeting_requests", "group_id")
    op.alter_column(
        "meeting_requests",
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'open'"),
        nullable=False,
    )
