"""Add durable per-user Telegram alert delivery records.

Revision ID: 20261022_01
Revises: None
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The application currently creates the base metadata during startup. On a
    # fresh database the referenced tables may not exist yet; create_all will
    # create this model table after the migration bootstrap has completed.
    if not inspector.has_table("jobs") or not inspector.has_table("telegram_users"):
        return
    if inspector.has_table("telegram_alert_deliveries"):
        return
    op.create_table(
        "telegram_alert_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "job_id", name="uq_telegram_alert_user_job"),
    )
    op.create_index(
        "ix_telegram_alert_delivery_status",
        "telegram_alert_deliveries",
        ["status"],
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("telegram_alert_deliveries"):
        op.drop_index("ix_telegram_alert_delivery_status", table_name="telegram_alert_deliveries")
        op.drop_table("telegram_alert_deliveries")
