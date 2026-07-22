"""push_subscriptions — browser Web Push registrations for offline alerts

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint   TEXT NOT NULL,
            p256dh     TEXT NOT NULL,
            auth       TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (endpoint)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_push_sub_user ON push_subscriptions(user_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS push_subscriptions CASCADE"))
