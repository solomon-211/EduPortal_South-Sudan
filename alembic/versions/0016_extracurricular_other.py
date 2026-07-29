"""extracurricular_other — a school isn't limited to the four fixed
extracurricular-activity checkboxes; anything beyond those can be
added freely as a comma-separated list of custom activities.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-25 00:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("schools", "extracurricular_other"):
        op.add_column("schools", sa.Column("extracurricular_other", sa.Text(), nullable=True))


def downgrade() -> None:
    if _col_exists("schools", "extracurricular_other"):
        op.drop_column("schools", "extracurricular_other")
