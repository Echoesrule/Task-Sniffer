"""Track Telegram alert claims and bounded retry times.

Revision ID: 20261022_03
Revises: 20261022_02
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_03"
down_revision = "20261022_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("telegram_alert_deliveries"):
        return
    present = {column["name"] for column in inspector.get_columns("telegram_alert_deliveries")}
    for name, type_ in (
        ("claim_token", sa.String(length=36)),
        ("claim_until", sa.DateTime(timezone=True)),
        ("next_attempt_at", sa.DateTime(timezone=True)),
        ("last_attempt_at", sa.DateTime(timezone=True)),
    ):
        if name not in present:
            op.add_column("telegram_alert_deliveries", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("telegram_alert_deliveries"):
        return
    present = {column["name"] for column in inspector.get_columns("telegram_alert_deliveries")}
    for name in ("last_attempt_at", "next_attempt_at", "claim_until", "claim_token"):
        if name in present:
            op.drop_column("telegram_alert_deliveries", name)
