"""announcement_attachments — file upload support for announcements

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-05 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

revision: str = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    if not _col_exists("announcements", "attachment_path"):
        op.add_column("announcements", sa.Column("attachment_path", sa.Text()))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite" and _col_exists("announcements", "attachment_path"):
        op.drop_column("announcements", "attachment_path")
