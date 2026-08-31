"""event participants identity model

Revision ID: c8d1e2f3a456
Revises: b7c8d9e0f112
Create Date: 2026-05-20 22:00:00.000000
"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d1e2f3a456"
down_revision: Union[str, None] = "b7c8d9e0f112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("profiles", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_profiles_email_lower", "profiles", [sa.text("lower(email)")], unique=False)

    op.add_column("participants", sa.Column("invite_token", sa.String(length=64), nullable=True))
    op.add_column(
        "participants",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'invited'"),
        ),
    )
    op.add_column("participants", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("participants", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM participants WHERE invite_token IS NULL")).fetchall()
    for row in rows:
        bind.execute(
            sa.text("UPDATE participants SET invite_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(32)[:48], "id": row[0]},
        )

    op.create_index(
        "uq_participants_invite_token",
        "participants",
        ["invite_token"],
        unique=True,
        postgresql_where=sa.text("invite_token IS NOT NULL"),
    )
    op.create_index(
        "uq_participants_event_email",
        "participants",
        ["meeting_request_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "uq_participants_event_user_id",
        "participants",
        ["meeting_request_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.add_column("proposal_responses", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("proposal_responses", "updated_at")

    op.drop_index("uq_participants_event_user_id", table_name="participants")
    op.drop_index("uq_participants_event_email", table_name="participants")
    op.drop_index("uq_participants_invite_token", table_name="participants")

    op.drop_column("participants", "updated_at")
    op.drop_column("participants", "email_verified_at")
    op.drop_column("participants", "source")
    op.drop_column("participants", "invite_token")

    op.drop_index("ix_profiles_email_lower", table_name="profiles")
    op.drop_column("profiles", "email_verified_at")
    op.drop_column("profiles", "email")
