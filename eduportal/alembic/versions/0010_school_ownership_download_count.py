"""school_ownership_download_count — public/private filter (FR 2.3) and
material download tracking for admin analytics (FR 10.1)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("schools", "ownership"):
        op.add_column("schools", sa.Column("ownership", sa.String(20), nullable=False, server_default="public"))
    if not _col_exists("materials", "download_count"):
        op.add_column("materials", sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"))

    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_schools_ownership ON schools(ownership)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_schools_ownership ON schools(ownership)"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(sa.text("DROP INDEX idx_schools_ownership ON schools"))
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS idx_schools_ownership"))
    if bind.dialect.name != "sqlite":
        if _col_exists("schools", "ownership"):
            op.drop_column("schools", "ownership")
        if _col_exists("materials", "download_count"):
            op.drop_column("materials", "download_count")
