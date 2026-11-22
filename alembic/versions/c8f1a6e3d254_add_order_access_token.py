"""add access_token to orders: the secret that opens a guest's receipt

Revision ID: c8f1a6e3d254
Revises: b7e2d4c91a03
Create Date: 2026-11-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f1a6e3d254"
down_revision: Union[str, Sequence[str], None] = "b7e2d4c91a03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("access_token", sa.String(length=64), nullable=True))
    # Every existing order gets its own random token (gen_random_uuid() is
    # built into PostgreSQL 13+ and uses a secure random source). Guests open
    # old receipts through their account, staff through the manager panel;
    # a guessed order number no longer shows anyone's details.
    op.execute(
        "UPDATE orders SET access_token = replace(gen_random_uuid()::text, '-', '') "
        "WHERE access_token IS NULL"
    )
    op.alter_column("orders", "access_token", nullable=False)


def downgrade() -> None:
    op.drop_column("orders", "access_token")
