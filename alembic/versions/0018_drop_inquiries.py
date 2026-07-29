"""drop_inquiries — removes the inquiries table now that the public
marketing site (contact/partner forms) that fed it has been removed.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS inquiries"))


def downgrade() -> None:
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
            resolved     INTEGER NOT NULL DEFAULT 0,
            resolved_by  INTEGER,
            resolved_at  TIMESTAMP,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_inquiries_kind ON inquiries(kind)"))
        op.execute(sa.text("CREATE INDEX idx_inquiries_created ON inquiries(created_at)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_inquiries_kind ON inquiries(kind)"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_inquiries_created ON inquiries(created_at)"))
