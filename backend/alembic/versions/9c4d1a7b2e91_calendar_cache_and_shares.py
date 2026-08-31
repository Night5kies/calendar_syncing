"""calendar cache and shares

Revision ID: 9c4d1a7b2e91
Revises: 3b5f2c9a1f47
Create Date: 2026-01-16 01:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c4d1a7b2e91"
down_revision: Union[str, None] = "3b5f2c9a1f47"
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
    op.add_column("calendar_connections", sa.Column("access_token", sa.Text(), nullable=True))
    op.add_column("calendar_connections", sa.Column("refresh_token", sa.Text(), nullable=True))
    op.create_index(
        "ix_calendar_connections_user_provider",
        "calendar_connections",
        ["user_id", "provider"],
        unique=False,
    )

    op.create_table(
        "provider_calendars",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_provider_calendars_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_calendar_id",
            name="uq_provider_calendars_user_provider_calendar",
        ),
    )
    op.create_index("ix_provider_calendars_user_id", "provider_calendars", ["user_id"], unique=False)

    op.create_table(
        "event_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("provider_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_all_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_event_cache_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_calendar_id",
            "provider_event_id",
            "start_at",
            "end_at",
            name="uq_event_cache_user_provider_event_instance",
        ),
    )
    op.create_index("ix_event_cache_user_start", "event_cache", ["user_id", "start_at"], unique=False)
    op.create_index("ix_event_cache_user_end", "event_cache", ["user_id", "end_at"], unique=False)
    op.create_index("ix_event_cache_user_last_fetched", "event_cache", ["user_id", "last_fetched_at"], unique=False)

    op.create_table(
        "busy_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            name="fk_busy_cache_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_busy_cache_user_start", "busy_cache", ["user_id", "start_at"], unique=False)

    op.create_table(
        "calendar_shares",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("viewer_id", sa.UUID(), nullable=False),
        sa.Column(
            "permission_level",
            sa.String(length=16),
            server_default=sa.text("'free_busy'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["profiles.id"],
            name="fk_calendar_shares_owner_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["viewer_id"],
            ["profiles.id"],
            name="fk_calendar_shares_viewer_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("owner_id", "viewer_id"),
        sa.UniqueConstraint("owner_id", "viewer_id", name="uq_calendar_shares_owner_viewer"),
    )
    op.create_check_constraint(
        "ck_calendar_shares_permission",
        "calendar_shares",
        "permission_level IN ('none', 'free_busy', 'details')",
    )
    op.create_index("ix_calendar_shares_owner_id", "calendar_shares", ["owner_id"], unique=False)
    op.create_index("ix_calendar_shares_viewer_id", "calendar_shares", ["viewer_id"], unique=False)

    op.execute("ALTER TABLE calendar_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_calendars ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_cache ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE busy_cache ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calendar_shares ENABLE ROW LEVEL SECURITY")

    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'calendar_connections_owner_rw'
        ) THEN
            CREATE POLICY calendar_connections_owner_rw ON calendar_connections
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        END IF;
        """
    )
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'provider_calendars_owner_rw'
        ) THEN
            CREATE POLICY provider_calendars_owner_rw ON provider_calendars
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        END IF;
        """
    )
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'event_cache_owner_rw'
        ) THEN
            CREATE POLICY event_cache_owner_rw ON event_cache
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        END IF;
        """
    )
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'busy_cache_owner_rw'
        ) THEN
            CREATE POLICY busy_cache_owner_rw ON busy_cache
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        END IF;
        """
    )
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'calendar_shares_owner_rw'
        ) THEN
            CREATE POLICY calendar_shares_owner_rw ON calendar_shares
            FOR ALL
            USING (owner_id = auth.uid())
            WITH CHECK (owner_id = auth.uid());
        END IF;
        """
    )
    _create_policy_if_auth_uid_exists(
        """
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'calendar_shares_viewer_read'
        ) THEN
            CREATE POLICY calendar_shares_viewer_read ON calendar_shares
            FOR SELECT
            USING (viewer_id = auth.uid());
        END IF;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS calendar_shares_viewer_read ON calendar_shares")
    op.execute("DROP POLICY IF EXISTS calendar_shares_owner_rw ON calendar_shares")
    op.execute("DROP POLICY IF EXISTS busy_cache_owner_rw ON busy_cache")
    op.execute("DROP POLICY IF EXISTS event_cache_owner_rw ON event_cache")
    op.execute("DROP POLICY IF EXISTS provider_calendars_owner_rw ON provider_calendars")
    op.execute("DROP POLICY IF EXISTS calendar_connections_owner_rw ON calendar_connections")

    op.drop_index("ix_calendar_shares_viewer_id", table_name="calendar_shares")
    op.drop_index("ix_calendar_shares_owner_id", table_name="calendar_shares")
    op.drop_constraint("ck_calendar_shares_permission", "calendar_shares", type_="check")
    op.drop_table("calendar_shares")

    op.drop_index("ix_busy_cache_user_start", table_name="busy_cache")
    op.drop_table("busy_cache")

    op.drop_index("ix_event_cache_user_last_fetched", table_name="event_cache")
    op.drop_index("ix_event_cache_user_end", table_name="event_cache")
    op.drop_index("ix_event_cache_user_start", table_name="event_cache")
    op.drop_table("event_cache")

    op.drop_index("ix_provider_calendars_user_id", table_name="provider_calendars")
    op.drop_table("provider_calendars")

    op.drop_index("ix_calendar_connections_user_provider", table_name="calendar_connections")
    op.drop_column("calendar_connections", "refresh_token")
    op.drop_column("calendar_connections", "access_token")
