"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id               {pk},
            name             TEXT NOT NULL,
            email            VARCHAR(255) UNIQUE,
            phone            VARCHAR(30) UNIQUE,
            password_hash    TEXT NOT NULL,
            role             VARCHAR(20) NOT NULL DEFAULT 'student',
            state            VARCHAR(100) NOT NULL DEFAULT '',
            county           VARCHAR(100) NOT NULL DEFAULT '',
            verified         INTEGER NOT NULL DEFAULT 1,
            notify_email     INTEGER NOT NULL DEFAULT 1,
            notify_sms       INTEGER NOT NULL DEFAULT 1,
            notify_inapp     INTEGER NOT NULL DEFAULT 1,
            avatar           TEXT,
            grade            VARCHAR(50) DEFAULT '',
            school_name      VARCHAR(200) DEFAULT '',
            child_school     VARCHAR(200) DEFAULT '',
            child_grade      VARCHAR(50) DEFAULT '',
            subjects         VARCHAR(300) DEFAULT '',
            institution      VARCHAR(200) DEFAULT '',
            experience_years INTEGER DEFAULT NULL,
            managed_school   VARCHAR(200) DEFAULT '',
            position         VARCHAR(100) DEFAULT '',
            school_id        INTEGER DEFAULT NULL,
            created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS schools (
            id           {pk},
            name         VARCHAR(200) NOT NULL,
            state        VARCHAR(100) NOT NULL,
            county       TEXT NOT NULL,
            level        VARCHAR(50) NOT NULL,
            type         VARCHAR(50) NOT NULL DEFAULT 'mixed',
            curriculum   VARCHAR(100) NOT NULL DEFAULT 'National',
            contact_name VARCHAR(100) NOT NULL DEFAULT '',
            phone        VARCHAR(30) NOT NULL DEFAULT '',
            email        TEXT,
            capacity     INTEGER,
            status       VARCHAR(30) NOT NULL DEFAULT 'open',
            enrollment   INTEGER DEFAULT 0,
            language     VARCHAR(50) DEFAULT 'English',
            boarding     VARCHAR(30) DEFAULT 'Day',
            hours        TEXT,
            description  TEXT,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS admission_requirements (
            id          {pk},
            school_id   INTEGER NOT NULL,
            item_label  TEXT NOT NULL,
            is_required INTEGER NOT NULL DEFAULT 1,
            notes       TEXT,
            FOREIGN KEY (school_id) REFERENCES schools(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS materials (
            id           {pk},
            title        TEXT NOT NULL,
            subject      VARCHAR(100) NOT NULL,
            grade        VARCHAR(50) NOT NULL,
            `year`       INTEGER NOT NULL,
            type         VARCHAR(50) NOT NULL,
            file_size    TEXT,
            preview_text TEXT,
            file_path    TEXT,
            uploaded_by  TEXT,
            approved     INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS announcements (
            id          {pk},
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

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS ngos (
            id          {pk},
            org_name    TEXT NOT NULL,
            contact     TEXT NOT NULL,
            email       TEXT,
            phone       TEXT,
            description TEXT,
            verified    INTEGER NOT NULL DEFAULT 1
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS scholarships (
            id            {pk},
            ngo_id        INTEGER,
            title         TEXT NOT NULL,
            description   TEXT NOT NULL,
            eligibility   TEXT NOT NULL,
            deadline      VARCHAR(20) NOT NULL,
            how_to_apply  TEXT NOT NULL,
            required_docs TEXT,
            external_link TEXT,
            approved      INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ngo_id) REFERENCES ngos(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS applications (
            id             {pk},
            user_id        INTEGER NOT NULL,
            scholarship_id INTEGER NOT NULL,
            status         VARCHAR(30) NOT NULL DEFAULT 'submitted',
            note           TEXT,
            applied_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, scholarship_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (scholarship_id) REFERENCES scholarships(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id        {pk},
            user_id   INTEGER NOT NULL,
            item_type VARCHAR(20) NOT NULL,
            item_id   INTEGER NOT NULL,
            saved_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, item_type, item_id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          {pk},
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
            user_id    INTEGER PRIMARY KEY,
            token      TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS invitations (
            id         {pk},
            token      TEXT,
            role       TEXT NOT NULL,
            ref_id     INTEGER,
            email      TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes — MySQL has no CREATE INDEX IF NOT EXISTS, but Alembic already
    # guarantees this migration runs at most once per database, so a plain
    # CREATE INDEX is safe there.
    indexes = [
        ("idx_users_email",           "users",        "email"),
        ("idx_users_phone",           "users",        "phone"),
        ("idx_schools_state",         "schools",      "state"),
        ("idx_apps_user",             "applications", "user_id"),
        ("idx_apps_sch",              "applications", "scholarship_id"),
        ("idx_bookmarks_user",        "bookmarks",    "user_id"),
        ("idx_materials_approved",    "materials",    "approved"),
        ("idx_scholarships_approved", "scholarships", "approved"),
    ]
    for name, table, cols in indexes:
        if bind.dialect.name == "mysql":
            op.execute(f"CREATE INDEX {name} ON {table}({cols})")
        else:
            op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({cols})")


def downgrade() -> None:
    for tbl in [
        "schema_migrations", "invitations", "password_resets", "audit_log",
        "bookmarks", "applications", "scholarships", "ngos",
        "announcements", "materials", "admission_requirements", "schools", "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl}")
