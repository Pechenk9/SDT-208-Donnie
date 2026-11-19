"""add tips, online payment and table orders

Revision ID: c3a9e5d17b42
Revises: 82e6a1841f3b
Create Date: 2026-11-19 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a9e5d17b42"
down_revision: Union[str, Sequence[str], None] = "82e6a1841f3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("table_number", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("tip_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("payment_method", sa.String(length=20), server_default="on_receipt", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("payment_status", sa.String(length=20), server_default="unpaid", nullable=False),
    )
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint("ck_orders_tip_amount", "orders", "tip_amount >= 0")
    op.create_check_constraint(
        "ck_orders_table_number",
        "orders",
        "table_number IS NULL OR (table_number >= 1 AND table_number <= 99)",
    )
    op.create_check_constraint(
        "ck_orders_payment_method",
        "orders",
        "payment_method IN ('on_receipt', 'online')",
    )
    op.create_check_constraint(
        "ck_orders_payment_status",
        "orders",
        "payment_status IN ('unpaid', 'pending', 'paid', 'failed', 'refunded')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_payment_status", "orders", type_="check")
    op.drop_constraint("ck_orders_payment_method", "orders", type_="check")
    op.drop_constraint("ck_orders_table_number", "orders", type_="check")
    op.drop_constraint("ck_orders_tip_amount", "orders", type_="check")
    op.drop_column("orders", "refunded_at")
    op.drop_column("orders", "paid_at")
    op.drop_column("orders", "payment_status")
    op.drop_column("orders", "payment_method")
    op.drop_column("orders", "tip_amount")
    op.drop_column("orders", "table_number")
