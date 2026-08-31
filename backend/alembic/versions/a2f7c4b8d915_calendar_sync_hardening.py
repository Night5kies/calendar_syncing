"""calendar sync hardening

Adds:
- `calendar_sync_state`, so an empty sync window is cacheable instead of
  re-hitting the provider on every request.
- `scheduled_events.artifact_sequence`, so a re-issued ICS carries an
  incrementing SEQUENCE and calendar clients treat it as an update.

Revision ID: a2f7c4b8d915
Revises: f1b4c7d9a623
Create Date: 2026-08-31 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2f7c4b8d915"
down_revision: Union[str, None] = "f1b4c7d9a623"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_policy_if_auth_uid_exists(policy_sql: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_namespace namespace
                JOIN pg_proc proc ON proc.pronamespace = namespace.oid
                WHERE namespace.nspname = 'auth'
                  AND proc.proname = 'uid'
            ) THEN
                {policy_sql}
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "calendar_sync_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_sync_state"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_calendar_sync_state_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "window_start",
            "window_end",
            name="uq_calendar_sync_state_window",
        ),
    )
    op.create_index(
        "ix_calendar_sync_state_user_provider",
        "calendar_sync_state",
        ["user_id", "provider"],
        unique=False,
    )

    op.execute("ALTER TABLE calendar_sync_state ENABLE ROW LEVEL SECURITY")
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'calendar_sync_state_owner_rw'
        ) THEN
            CREATE POLICY calendar_sync_state_owner_rw ON calendar_sync_state
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        END IF;
        """
    )

    op.add_column(
        "scheduled_events",
        sa.Column(
            "artifact_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_events", "artifact_sequence")
    op.execute("DROP POLICY IF EXISTS calendar_sync_state_owner_rw ON calendar_sync_state")
    op.drop_index("ix_calendar_sync_state_user_provider", table_name="calendar_sync_state")
    op.drop_table("calendar_sync_state")
