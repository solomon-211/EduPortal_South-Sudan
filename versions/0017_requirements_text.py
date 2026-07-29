"""requirements_text — replaces the itemised per-row admission
requirements editor with a single pasteable text field, used
alongside the requirements_doc_url PDF attachment added in 0015.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("schools", "requirements_text"):
        op.add_column("schools", sa.Column("requirements_text", sa.Text(), nullable=True))


def downgrade() -> None:
    if _col_exists("schools", "requirements_text"):
        op.drop_column("schools", "requirements_text")
