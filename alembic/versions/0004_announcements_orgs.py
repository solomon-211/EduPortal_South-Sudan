"""announcements_orgs — verified org publishers + expanded announcements

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-04 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

revision: str = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ORG_TYPES = (
    "Ministry of General Education",
    "State Ministry of Education",
    "University",
    "College",
    "School",
    "Examination Body",
    "NGO",
    "Scholarship Provider",
)


def _col_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # Verified organisations table
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS organizations (
            id           {pk},
            name         TEXT NOT NULL,
            org_type     VARCHAR(100) NOT NULL,
            state        VARCHAR(100),
            email        TEXT,
            phone        TEXT,
            website      TEXT,
            description  TEXT,
            verified     INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if bind.dialect.name == "mysql":
        op.execute("CREATE INDEX idx_orgs_type ON organizations(org_type)")
        op.execute("CREATE INDEX idx_orgs_verified ON organizations(verified)")
    else:
        op.execute("CREATE INDEX IF NOT EXISTS idx_orgs_type    ON organizations(org_type)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_orgs_verified ON organizations(verified)")

    # Expand announcements table — add columns only if they don't already exist
    for col, column in [
        ("org_type",       sa.Column("org_type", sa.String(100))),
        ("org_name",       sa.Column("org_name", sa.Text())),
        ("org_id",         sa.Column("org_id", sa.Integer())),
        ("priority",       sa.Column("priority", sa.String(20), nullable=False, server_default="normal")),
        ("attachment_url", sa.Column("attachment_url", sa.Text())),
        ("state",          sa.Column("state", sa.String(100))),
    ]:
        if not _col_exists("announcements", col):
            op.add_column("announcements", column)

    if bind.dialect.name == "mysql":
        op.execute("CREATE INDEX idx_ann_org_type ON announcements(org_type)")
        op.execute("CREATE INDEX idx_ann_priority  ON announcements(priority)")
        op.execute("CREATE INDEX idx_ann_state     ON announcements(state)")
    else:
        op.execute("CREATE INDEX IF NOT EXISTS idx_ann_org_type ON announcements(org_type)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_ann_priority  ON announcements(priority)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_ann_state     ON announcements(state)")

    # Seed sample organisations
    seed_sql = """
        INSERT{ignore} INTO organizations (name, org_type, state, email, verified)
        VALUES
          ('Ministry of General Education and Instruction', 'Ministry of General Education', 'National', 'info@moe.gov.ss', 1),
          ('South Sudan National Examinations Council',     'Examination Body',              'National', 'info@ssnec.gov.ss', 1),
          ('University of Juba',                           'University',                    'Central Equatoria', 'info@uoj.edu.ss', 1),
          ('Upper Nile University',                        'University',                    'Upper Nile', 'info@unu.edu.ss', 1)
        {conflict_clause}
    """
    if bind.dialect.name == "mysql":
        op.execute(seed_sql.format(ignore=" IGNORE", conflict_clause=""))
    else:
        op.execute(seed_sql.format(ignore="", conflict_clause="ON CONFLICT DO NOTHING"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS organizations")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for col in ("org_type", "org_name", "org_id", "priority", "attachment_url", "state"):
            if _col_exists("announcements", col):
                op.drop_column("announcements", col)
