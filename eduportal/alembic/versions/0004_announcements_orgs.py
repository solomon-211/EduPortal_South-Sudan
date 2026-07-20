"""announcements_orgs — verified org publishers + expanded announcements

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-04 00:00:00.000000
"""
from __future__ import annotations
from alembic import op

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


def upgrade() -> None:
    # ── Verified organisations table ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id           SERIAL PRIMARY KEY,
            name         TEXT NOT NULL,
            org_type     TEXT NOT NULL,
            state        TEXT,
            email        TEXT,
            phone        TEXT,
            website      TEXT,
            description  TEXT,
            verified     INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_orgs_type    ON organizations(org_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orgs_verified ON organizations(verified)")

    # ── Expand announcements table ────────────────────────────────────────────
    # Add columns only if they don't exist (idempotent via DO block)
    for col, definition in [
        ("org_type",       "TEXT"),
        ("org_name",       "TEXT"),
        ("org_id",         "INTEGER"),
        ("priority",       "TEXT NOT NULL DEFAULT 'normal'"),
        ("attachment_url", "TEXT"),
        ("state",          "TEXT"),
    ]:
        op.execute(f"""
            DO $$ BEGIN
                ALTER TABLE announcements ADD COLUMN {col} {definition};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_ann_org_type ON announcements(org_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ann_priority  ON announcements(priority)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ann_state     ON announcements(state)")

    # ── Seed sample organisations ─────────────────────────────────────────────
    op.execute("""
        INSERT INTO organizations (name, org_type, state, email, verified)
        VALUES
          ('Ministry of General Education and Instruction', 'Ministry of General Education', 'National', 'info@moe.gov.ss', 1),
          ('South Sudan National Examinations Council',     'Examination Body',              'National', 'info@ssnec.gov.ss', 1),
          ('University of Juba',                           'University',                    'Central Equatoria', 'info@uoj.edu.ss', 1),
          ('Upper Nile University',                        'University',                    'Upper Nile', 'info@unu.edu.ss', 1)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
    for col in ("org_type", "org_name", "org_id", "priority", "attachment_url", "state"):
        op.execute(f"""
            DO $$ BEGIN
                ALTER TABLE announcements DROP COLUMN {col};
            EXCEPTION WHEN undefined_column THEN NULL;
            END $$;
        """)
