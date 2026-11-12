"""Add user roles, token revocation, and Telegram link challenges.

Revision ID: 20261112_01
Revises: 20261022_03
Create Date: 2026-11-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261112_01"
down_revision = "20261022_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("users"):
        present = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in present:
            op.add_column(
                "users",
                sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
            )
        if "token_version" not in present:
            op.add_column(
                "users",
                sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            )

    if not inspector.has_table("telegram_link_codes"):
        op.create_table(
            "telegram_link_codes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_telegram_link_codes_user_id", "telegram_link_codes", ["user_id"])
        op.create_index(
            "ix_telegram_link_codes_code_hash",
            "telegram_link_codes",
            ["code_hash"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telegram_link_codes"):
        op.drop_table("telegram_link_codes")
    if inspector.has_table("users"):
        present = {column["name"] for column in inspector.get_columns("users")}
        if "token_version" in present:
            op.drop_column("users", "token_version")
        if "role" in present:
            op.drop_column("users", "role")
