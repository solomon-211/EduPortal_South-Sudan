"""inquiries — public contact/partner form submissions from the marketing site

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS inquiries (
            id           {pk},
            kind         VARCHAR(20) NOT NULL,
            name         VARCHAR(200) NOT NULL,
            email        VARCHAR(120) NOT NULL,
            phone        VARCHAR(30),
            organization VARCHAR(200),
            subject      VARCHAR(200),
            message      TEXT,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_inquiries_kind ON inquiries(kind)"))
        op.execute(sa.text("CREATE INDEX idx_inquiries_created ON inquiries(created_at)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_inquiries_kind ON inquiries(kind)"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_inquiries_created ON inquiries(created_at)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS inquiries"))
