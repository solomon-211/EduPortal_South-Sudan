"""requirements_document — lets a school attach a single admission
requirements document (PDF/image) alongside the existing itemised
text checklist, instead of only being able to type requirements out.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("schools", "requirements_doc_url"):
        op.add_column("schools", sa.Column("requirements_doc_url", sa.String(length=300), nullable=True))


def downgrade() -> None:
    if _col_exists("schools", "requirements_doc_url"):
        op.drop_column("schools", "requirements_doc_url")
