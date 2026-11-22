"""add receipt_emailed_at to orders: when the payment receipt was emailed

Revision ID: b7e2d4c91a03
Revises: f3a9c2e6b815
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2d4c91a03"
down_revision: Union[str, Sequence[str], None] = "f3a9c2e6b815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("receipt_emailed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Orders paid before receipts existed count as done: opening one of
    # their receipts later must not email a guest about an old payment.
    op.execute(
        "UPDATE orders SET receipt_emailed_at = COALESCE(paid_at, created_at) "
        "WHERE payment_status IN ('paid', 'refunded')"
    )


def downgrade() -> None:
    op.drop_column("orders", "receipt_emailed_at")
