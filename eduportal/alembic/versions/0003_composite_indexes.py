"""Add composite indexes for the most common query patterns.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_INDEXES = [
    ("idx_ann_approved_date",           "announcements(approved, created_at DESC)"),
    ("idx_mat_approved_subject_grade",  "materials(approved, subject, grade)"),
    ("idx_mat_year_type",               "materials(year DESC, type)"),
    ("idx_sch_approved_deadline",       "scholarships(approved, deadline ASC)"),
    ("idx_apps_user_date",              "applications(user_id, applied_at DESC)"),
    ("idx_apps_status",                 "applications(status)"),
    ("idx_bookmarks_user_type",         "bookmarks(user_id, item_type)"),
    ("idx_pr_token_hint",               "password_resets(token)"),
    ("idx_schools_name",                "schools(name)"),
    ("idx_schools_state_level_type",    "schools(state, level, type)"),
]


def upgrade() -> None:
    for name, definition in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {definition}")


def downgrade() -> None:
    for name, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
