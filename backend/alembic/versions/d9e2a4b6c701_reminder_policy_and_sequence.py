"""reminder policy + sequence idempotency

Revision ID: d9e2a4b6c701
Revises: c8d1e2f3a456
Create Date: 2026-05-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d9e2a4b6c701"
down_revision: Union[str, None] = "c8d1e2f3a456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_requests",
        sa.Column("reminder_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "reminder_logs",
        sa.Column(
            "reminder_sequence",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE reminder_logs rl
            SET reminder_sequence = sub.seq
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY meeting_request_id, participant_id
                           ORDER BY created_at, id
                       ) AS seq
                FROM reminder_logs
            ) sub
            WHERE rl.id = sub.id
            """
        )
    )

    op.create_unique_constraint(
        "uq_reminder_logs_request_participant_sequence",
        "reminder_logs",
        ["meeting_request_id", "participant_id", "reminder_sequence"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_reminder_logs_request_participant_sequence",
        "reminder_logs",
        type_="unique",
    )
    op.drop_column("reminder_logs", "reminder_sequence")
    op.drop_column("meeting_requests", "reminder_policy")
