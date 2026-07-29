"""ngo_scholarship_fields — the "essential fields" set for NGO/scholarship-
provider profiles (identity, mission, contact/location) and scholarship
listings (slots, coverage, contact person), plus a programs table.

Revision ID: 0013
Revises: 0012
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


revision: str = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

NGO_COLUMNS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("registration_number", sa.String(80), None),
    ("year_founded", sa.Integer(), None),
    ("logo_url", sa.String(300), None),
    ("org_type", sa.String(80), None),
    ("areas_of_focus", sa.Text(), None),
    ("state", sa.String(80), None),
    ("county", sa.String(80), None),
    ("website", sa.String(300), None),
    ("mission", sa.Text(), None),
    ("vision", sa.Text(), None),
    ("core_values", sa.Text(), None),
    ("registration_verified", sa.Integer(), "0"),
]

SCHOLARSHIP_COLUMNS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("slots_available", sa.Integer(), None),
    ("whats_covered", sa.Text(), None),
    ("contact_person", sa.String(150), None),
    ("rejection_reason", sa.Text(), None),
]


def upgrade() -> None:
    for name, col_type, default in NGO_COLUMNS:
        if _col_exists("ngos", name):
            continue
        if default is None:
            op.add_column("ngos", sa.Column(name, col_type, nullable=True))
        else:
            op.add_column("ngos", sa.Column(name, col_type, nullable=False, server_default=default))

    for name, col_type, default in SCHOLARSHIP_COLUMNS:
        if _col_exists("scholarships", name):
            continue
        if default is None:
            op.add_column("scholarships", sa.Column(name, col_type, nullable=True))
        else:
            op.add_column("scholarships", sa.Column(name, col_type, nullable=False, server_default=default))

    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS ngo_programs (
            id                     {pk},
            ngo_id                 INTEGER NOT NULL,
            name                   VARCHAR(200) NOT NULL,
            target_beneficiaries   VARCHAR(300),
            geographic_coverage    VARCHAR(300),
            beneficiaries_per_year INTEGER,
            FOREIGN KEY (ngo_id) REFERENCES ngos(id) ON DELETE CASCADE
        )
    """))

    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_ngo_programs_ngo ON ngo_programs(ngo_id)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_ngo_programs_ngo ON ngo_programs(ngo_id)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS ngo_programs"))
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for name, _type, _default in NGO_COLUMNS:
            if _col_exists("ngos", name):
                op.drop_column("ngos", name)
        for name, _type, _default in SCHOLARSHIP_COLUMNS:
            if _col_exists("scholarships", name):
                op.drop_column("scholarships", name)
