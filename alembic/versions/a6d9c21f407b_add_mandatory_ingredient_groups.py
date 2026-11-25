"""add mandatory selection flag to ingredient groups

Revision ID: a6d9c21f407b
Revises: 9e6d1bc04a72
Create Date: 2026-11-24 17:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6d9c21f407b"
down_revision: Union[str, Sequence[str], None] = "9e6d1bc04a72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingredient_groups",
        sa.Column(
            "is_mandatory",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ingredient_groups", "is_mandatory")
