"""restore order receipt fields omitted by the i18n preparation revision

Revision ID: 9e6d1bc04a72
Revises: 026c888f045f
Create Date: 2026-11-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e6d1bc04a72"
down_revision: Union[str, Sequence[str], None] = "026c888f045f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns("orders")
    }

    if "access_token" not in columns:
        op.add_column(
            "orders",
            sa.Column("access_token", sa.String(length=64), nullable=True),
        )
        columns["access_token"] = {"nullable": True}

    if columns["access_token"]["nullable"]:
        op.execute(
            "UPDATE orders "
            "SET access_token = replace(gen_random_uuid()::text, '-', '') "
            "WHERE access_token IS NULL"
        )
        op.alter_column(
            "orders",
            "access_token",
            existing_type=sa.String(length=64),
            nullable=False,
        )

    if "receipt_emailed_at" not in columns:
        op.add_column(
            "orders",
            sa.Column(
                "receipt_emailed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        # The previous column was dropped, so sent status cannot be recovered.
        # Match the original migration's conservative treatment of old payments.
        op.execute(
            "UPDATE orders "
            "SET receipt_emailed_at = COALESCE(paid_at, created_at) "
            "WHERE payment_status IN ('paid', 'refunded')"
        )


def downgrade() -> None:
    # These columns belong to earlier revisions and are part of the schema
    # expected at 026c888f045f; keep them when downgrading only this repair.
    pass
