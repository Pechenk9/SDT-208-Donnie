"""add LiqPay payments: payment attempt on orders, demo payments table

Revision ID: f3a9c2e6b815
Revises: d4b7f2a91c60
Create Date: 2026-11-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a9c2e6b815"
down_revision: Union[str, Sequence[str], None] = "d4b7f2a91c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_reference", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("payment_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("orders", sa.Column("payment_provider_id", sa.String(length=64), nullable=True))
    op.create_index("ix_orders_payment_reference", "orders", ["payment_reference"])

    op.create_table(
        "demo_liqpay_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_url", sa.Text(), nullable=False),
        sa.Column("server_url", sa.Text(), nullable=True),
        sa.Column("card_mask", sa.String(length=32), nullable=True),
        sa.Column("err_code", sa.String(length=50), nullable=True),
        sa.Column("err_description", sa.String(length=255), nullable=True),
        sa.Column("create_date", sa.BigInteger(), nullable=False),
        sa.Column("end_date", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_demo_liqpay_payments_order_id", "demo_liqpay_payments", ["order_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_demo_liqpay_payments_order_id", table_name="demo_liqpay_payments")
    op.drop_table("demo_liqpay_payments")
    op.drop_index("ix_orders_payment_reference", table_name="orders")
    op.drop_column("orders", "payment_provider_id")
    op.drop_column("orders", "payment_amount")
    op.drop_column("orders", "payment_reference")
