"""add login sessions

Revision ID: 82e6a1841f3b
Revises: fde77ced2db1
Create Date: 2026-11-17 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "82e6a1841f3b"
down_revision: Union[str, Sequence[str], None] = "fde77ced2db1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        "ix_login_sessions_user_id",
        "login_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_login_sessions_user_id", table_name="login_sessions")
    op.drop_table("login_sessions")
