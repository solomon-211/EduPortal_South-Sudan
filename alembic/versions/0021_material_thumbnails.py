"""material_thumbnails — a real preview image generated from the uploaded
file itself (first PDF page, or a frame pulled from the video), shown at
the top of each materials card in place of the generic video/PDF icon.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


revision: str = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("materials", "thumbnail_path"):
        op.add_column("materials", sa.Column("thumbnail_path", sa.Text(), nullable=True))


def downgrade() -> None:
    if _col_exists("materials", "thumbnail_path"):
        op.drop_column("materials", "thumbnail_path")
