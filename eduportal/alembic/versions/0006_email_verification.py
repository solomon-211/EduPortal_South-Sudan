"""email_verification — token table for registration email confirmation

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-06 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            token      TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_email_verif_token ON email_verifications(token)"
    ))

    # Existing users are already active — mark them verified
    op.execute(sa.text("UPDATE users SET verified=1 WHERE verified=0"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS email_verifications CASCADE"))
