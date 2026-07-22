"""notification_refs — optional ref_type/ref_id on notifications for dedup and linking

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("notifications", "ref_type"):
        op.add_column("notifications", sa.Column("ref_type", sa.Text()))
    if not _col_exists("notifications", "ref_id"):
        op.add_column("notifications", sa.Column("ref_id", sa.Integer()))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_notif_ref ON notifications(user_id, type, ref_type, ref_id)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TABLE notifications DROP COLUMN IF EXISTS ref_type"))
        bind.execute(sa.text("ALTER TABLE notifications DROP COLUMN IF EXISTS ref_id"))
