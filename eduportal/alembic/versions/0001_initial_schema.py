"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id               SERIAL PRIMARY KEY,
            name             TEXT NOT NULL,
            email            TEXT UNIQUE,
            phone            TEXT UNIQUE,
            password_hash    TEXT NOT NULL,
            role             TEXT NOT NULL DEFAULT 'student',
            state            TEXT NOT NULL DEFAULT '',
            county           TEXT NOT NULL DEFAULT '',
            verified         INTEGER NOT NULL DEFAULT 1,
            notify_email     INTEGER NOT NULL DEFAULT 1,
            notify_sms       INTEGER NOT NULL DEFAULT 1,
            notify_inapp     INTEGER NOT NULL DEFAULT 1,
            avatar           TEXT DEFAULT NULL,
            grade            TEXT DEFAULT '',
            school_name      TEXT DEFAULT '',
            child_school     TEXT DEFAULT '',
            child_grade      TEXT DEFAULT '',
            subjects         TEXT DEFAULT '',
            institution      TEXT DEFAULT '',
            experience_years INTEGER DEFAULT NULL,
            managed_school   TEXT DEFAULT '',
            position         TEXT DEFAULT '',
            school_id        INTEGER DEFAULT NULL,
            created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            id           SERIAL PRIMARY KEY,
            name         TEXT NOT NULL,
            state        TEXT NOT NULL,
            county       TEXT NOT NULL,
            level        TEXT NOT NULL,
            type         TEXT NOT NULL DEFAULT 'mixed',
            curriculum   TEXT NOT NULL DEFAULT 'National',
            contact_name TEXT NOT NULL DEFAULT '',
            phone        TEXT NOT NULL DEFAULT '',
            email        TEXT,
            capacity     INTEGER,
            status       TEXT NOT NULL DEFAULT 'open',
            enrollment   INTEGER DEFAULT 0,
            language     TEXT DEFAULT 'English',
            boarding     TEXT DEFAULT 'Day',
            hours        TEXT,
            description  TEXT,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS admission_requirements (
            id          SERIAL PRIMARY KEY,
            school_id   INTEGER NOT NULL REFERENCES schools(id),
            item_label  TEXT NOT NULL,
            is_required INTEGER NOT NULL DEFAULT 1,
            notes       TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id           SERIAL PRIMARY KEY,
            title        TEXT NOT NULL,
            subject      TEXT NOT NULL,
            grade        TEXT NOT NULL,
            year         INTEGER NOT NULL,
            type         TEXT NOT NULL,
            file_size    TEXT,
            preview_text TEXT,
            file_path    TEXT,
            uploaded_by  TEXT,
            approved     INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id          SERIAL PRIMARY KEY,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id   INTEGER,
            audience    TEXT NOT NULL,
            expires_at  TEXT,
            approved    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ngos (
            id          SERIAL PRIMARY KEY,
            org_name    TEXT NOT NULL,
            contact     TEXT NOT NULL,
            email       TEXT,
            phone       TEXT,
            description TEXT,
            verified    INTEGER NOT NULL DEFAULT 1
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS scholarships (
            id            SERIAL PRIMARY KEY,
            ngo_id        INTEGER REFERENCES ngos(id),
            title         TEXT NOT NULL,
            description   TEXT NOT NULL,
            eligibility   TEXT NOT NULL DEFAULT '',
            deadline      TEXT NOT NULL,
            how_to_apply  TEXT NOT NULL DEFAULT '',
            required_docs TEXT,
            external_link TEXT,
            approved      INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            scholarship_id INTEGER NOT NULL REFERENCES scholarships(id),
            status         TEXT NOT NULL DEFAULT 'submitted',
            note           TEXT,
            applied_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, scholarship_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id        SERIAL PRIMARY KEY,
            user_id   INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id   INTEGER NOT NULL,
            saved_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, item_type, item_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          SERIAL PRIMARY KEY,
            admin_id    INTEGER,
            action      TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id   INTEGER,
            note        TEXT,
            timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id),
            token      TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            id         SERIAL PRIMARY KEY,
            token      TEXT NOT NULL UNIQUE,
            role       TEXT NOT NULL,
            ref_id     INTEGER,
            email      TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email           ON users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_phone           ON users(phone)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_schools_state         ON schools(state)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_apps_user             ON applications(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_apps_sch              ON applications(scholarship_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user        ON bookmarks(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_materials_approved    ON materials(approved)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarships_approved ON scholarships(approved)")


def downgrade() -> None:
    for tbl in [
        "schema_migrations", "invitations", "password_resets", "audit_log",
        "bookmarks", "applications", "scholarships", "ngos",
        "announcements", "materials", "admission_requirements", "schools", "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
