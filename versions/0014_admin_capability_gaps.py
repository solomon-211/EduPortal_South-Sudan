"""admin_capability_gaps — schema support for the platform-administrator
capability audit: rejection reasons on the remaining moderated tables,
announcement view counts, ngo_officer account linkage (mirrors school_id),
inquiry resolution tracking, and a backup-run visibility log.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-24 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("materials", "rejection_reason"):
        op.add_column("materials", sa.Column("rejection_reason", sa.Text(), nullable=True))

    if not _col_exists("announcements", "rejection_reason"):
        op.add_column("announcements", sa.Column("rejection_reason", sa.Text(), nullable=True))
    if not _col_exists("announcements", "view_count"):
        op.add_column("announcements", sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"))

    if not _col_exists("users", "ngo_id"):
        op.add_column("users", sa.Column("ngo_id", sa.Integer(), nullable=True))

    if not _col_exists("inquiries", "resolved"):
        op.add_column("inquiries", sa.Column("resolved", sa.Integer(), nullable=False, server_default="0"))
    if not _col_exists("inquiries", "resolved_by"):
        op.add_column("inquiries", sa.Column("resolved_by", sa.Integer(), nullable=True))
    if not _col_exists("inquiries", "resolved_at"):
        op.add_column("inquiries", sa.Column("resolved_at", sa.DateTime(), nullable=True))

    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts_default = "CURRENT_TIMESTAMP" if bind.dialect.name == "mysql" else "CURRENT_TIMESTAMP"

    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS backup_runs (
            id         {pk},
            ran_at     TIMESTAMP NOT NULL DEFAULT {ts_default},
            success    INTEGER NOT NULL DEFAULT 1,
            file_path  VARCHAR(400),
            file_size  INTEGER,
            message    TEXT
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS backup_runs"))
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for table, col in [
            ("materials", "rejection_reason"),
            ("announcements", "rejection_reason"),
            ("announcements", "view_count"),
            ("users", "ngo_id"),
            ("inquiries", "resolved"),
            ("inquiries", "resolved_by"),
            ("inquiries", "resolved_at"),
        ]:
            if _col_exists(table, col):
                op.drop_column(table, col)
