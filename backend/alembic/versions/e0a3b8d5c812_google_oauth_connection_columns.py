"""calendar_connections oauth columns

Revision ID: e0a3b8d5c812
Revises: d9e2a4b6c701
Create Date: 2026-05-26 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0a3b8d5c812"
down_revision: Union[str, None] = "d9e2a4b6c701"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("calendar_connections", sa.Column("provider_email", sa.String(length=320), nullable=True))
    op.add_column("calendar_connections", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calendar_connections", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_connections", "updated_at")
    op.drop_column("calendar_connections", "expires_at")
    op.drop_column("calendar_connections", "provider_email")
