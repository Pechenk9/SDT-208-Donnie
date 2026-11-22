"""add celebration add-ons and pre-order time slots to orders

Revision ID: d4b7f2a91c60
Revises: c3a9e5d17b42
Create Date: 2026-11-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b7f2a91c60"
down_revision: Union[str, Sequence[str], None] = "c3a9e5d17b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("gift_box", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("candles", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("postcard_message", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("extras_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
    )
    op.add_column("orders", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("time_slot", sa.String(length=20), nullable=True))

    op.create_check_constraint(
        "ck_orders_candles", "orders", "candles >= 0 AND candles <= 24"
    )
    op.create_check_constraint(
        "ck_orders_extras_amount", "orders", "extras_amount >= 0"
    )
    op.create_check_constraint(
        "ck_orders_schedule_pair",
        "orders",
        "(scheduled_date IS NULL) = (time_slot IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_schedule_pair", "orders", type_="check")
    op.drop_constraint("ck_orders_extras_amount", "orders", type_="check")
    op.drop_constraint("ck_orders_candles", "orders", type_="check")
    op.drop_column("orders", "time_slot")
    op.drop_column("orders", "scheduled_date")
    op.drop_column("orders", "extras_amount")
    op.drop_column("orders", "postcard_message")
    op.drop_column("orders", "candles")
    op.drop_column("orders", "gift_box")
