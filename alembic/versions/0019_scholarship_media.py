"""scholarship_media — lets an NGO attach a poster image and a promo
video to a scholarship listing, the same way schools/NGOs already
attach a logo and materials already attach a video file.

Revision ID: 0019
Revises: 0018
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


revision: str = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("scholarships", "poster_image_url"):
        op.add_column("scholarships", sa.Column("poster_image_url", sa.String(300), nullable=True))
    if not _col_exists("scholarships", "video_path"):
        op.add_column("scholarships", sa.Column("video_path", sa.String(300), nullable=True))


def downgrade() -> None:
    if _col_exists("scholarships", "video_path"):
        op.drop_column("scholarships", "video_path")
    if _col_exists("scholarships", "poster_image_url"):
        op.drop_column("scholarships", "poster_image_url")
