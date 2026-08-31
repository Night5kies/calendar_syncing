"""confirmation artifacts

Revision ID: b7c8d9e0f112
Revises: a6d9c3e4f201
Create Date: 2026-03-18 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f112"
down_revision: Union[str, None] = "a6d9c3e4f201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scheduled_events", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("scheduled_events", sa.Column("provider_event_id", sa.String(length=255), nullable=True))
    op.add_column("scheduled_events", sa.Column("artifact_path", sa.String(length=500), nullable=True))
    op.add_column("scheduled_events", sa.Column("artifact_uid", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_events", "artifact_uid")
    op.drop_column("scheduled_events", "artifact_path")
    op.drop_column("scheduled_events", "provider_event_id")
    op.drop_column("scheduled_events", "provider")
