"""school_profile_fields — the full "essential fields" set for school
profiles (identity, mission, academics, admissions, staff, facilities,
extracurriculars), a moderation/approval gate for self-submitted schools,
and a per-year exam results table.

Revision ID: 0012
Revises: 0011
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


revision: str = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# (column name, SQLAlchemy type, server_default or None for a nullable
# text/number field with no default)
NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("registration_number", sa.String(80), None),
    ("year_established", sa.Integer(), None),
    ("logo_url", sa.String(300), None),
    ("address", sa.String(300), None),
    ("mission", sa.Text(), None),
    ("vision", sa.Text(), None),
    ("core_values", sa.Text(), None),
    ("subjects_offered", sa.Text(), None),
    ("age_requirements", sa.String(200), None),
    ("entry_grades", sa.String(200), None),
    ("fees_structure", sa.Text(), None),
    ("how_to_apply", sa.Text(), None),
    ("headteacher_name", sa.String(150), None),
    ("teaching_staff_count", sa.Integer(), None),
    ("classroom_count", sa.Integer(), None),
    ("has_library", sa.Integer(), "0"),
    ("has_laboratory", sa.Integer(), "0"),
    ("has_sports_facilities", sa.Integer(), "0"),
    ("has_water_sanitation", sa.Integer(), "0"),
    ("has_electricity", sa.Integer(), "0"),
    ("has_sports_clubs", sa.Integer(), "0"),
    ("has_arts_culture", sa.Integer(), "0"),
    ("has_academic_clubs", sa.Integer(), "0"),
    ("has_student_government", sa.Integer(), "0"),
    # Moderation: existing/admin-onboarded schools default to already-approved
    # (approved=1) so nothing already live goes dark; only the self-service
    # POST /api/schools path sets this to 0 for new submissions going forward.
    ("approved", sa.Integer(), "1"),
    ("registration_verified", sa.Integer(), "0"),
    ("rejection_reason", sa.Text(), None),
]


def upgrade() -> None:
    for name, col_type, default in NEW_COLUMNS:
        if _col_exists("schools", name):
            continue
        if default is None:
            op.add_column("schools", sa.Column(name, col_type, nullable=True))
        else:
            op.add_column("schools", sa.Column(name, col_type, nullable=False, server_default=default))

    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS school_exam_results (
            id         {pk},
            school_id  INTEGER NOT NULL,
            year       INTEGER NOT NULL,
            subject    VARCHAR(80) NOT NULL,
            pass_rate  DECIMAL(5,2) NOT NULL,
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
        )
    """))

    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_schools_approved ON schools(approved)"))
        op.execute(sa.text("CREATE INDEX idx_exam_results_school ON school_exam_results(school_id)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_schools_approved ON schools(approved)"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_exam_results_school ON school_exam_results(school_id)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS school_exam_results"))
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(sa.text("DROP INDEX idx_schools_approved ON schools"))
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS idx_schools_approved"))
    if bind.dialect.name != "sqlite":
        for name, _type, _default in NEW_COLUMNS:
            if _col_exists("schools", name):
                op.drop_column("schools", name)
