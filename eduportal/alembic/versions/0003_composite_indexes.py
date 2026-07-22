"""Add composite indexes for the most common query patterns.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_INDEXES = [
    ("idx_ann_approved_date",           "announcements", "approved, created_at DESC"),
    ("idx_mat_approved_subject_grade",  "materials",      "approved, subject, grade"),
    ("idx_mat_year_type",               "materials",      "`year` DESC, type"),
    ("idx_sch_approved_deadline",       "scholarships",   "approved, deadline ASC"),
    ("idx_apps_user_date",              "applications",   "user_id, applied_at DESC"),
    ("idx_apps_status",                 "applications",   "status"),
    ("idx_bookmarks_user_type",         "bookmarks",      "user_id, item_type"),
    ("idx_schools_name",                "schools",        "name"),
    ("idx_schools_state_level_type",    "schools",        "state, level, type"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, table, cols in _INDEXES:
        if bind.dialect.name == "mysql":
            op.execute(sa.text(f"CREATE INDEX {name} ON {table}({cols})"))
        else:
            op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({cols})"))


def downgrade() -> None:
    bind = op.get_bind()
    for name, table, _ in _INDEXES:
        if bind.dialect.name == "mysql":
            op.execute(sa.text(f"DROP INDEX {name} ON {table}"))
        else:
            op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
