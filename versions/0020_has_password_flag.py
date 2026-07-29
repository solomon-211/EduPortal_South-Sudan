"""has_password_flag — an account created via "Continue with Google" gets a
random, unknowable placeholder password_hash (the column is NOT NULL) so it
never had a real password to log in with via the credentials form. This
flag lets /api/login tell that case apart from a genuinely wrong password
and point the user at Google sign-in or the reset-password flow instead.

Revision ID: 0020
Revises: 0019
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


revision: str = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _col_exists("users", "has_password"):
        op.add_column("users", sa.Column("has_password", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    if _col_exists("users", "has_password"):
        op.drop_column("users", "has_password")
