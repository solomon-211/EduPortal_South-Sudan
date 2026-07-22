"""refresh_tokens — long-lived tokens for silent access-token renewal

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id         {pk},
            user_id    INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            token_hint VARCHAR(16) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """))
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_refresh_hint ON refresh_tokens(token_hint)"))
        op.execute(sa.text("CREATE INDEX idx_refresh_user ON refresh_tokens(user_id)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_refresh_hint ON refresh_tokens(token_hint)"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS refresh_tokens"))
