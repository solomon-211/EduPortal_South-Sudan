"""Fix invitations schema and add role_permissions table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Fix invitations table ─────────────────────────────────────────────────
    # Original schema used a plaintext `token` column.
    # App now stores a bcrypt hash (token_hash) and an 8-char hint (token_hint)
    # for fast index lookups without leaking the full token in the database.
    op.execute("""
        DO $$
        BEGIN
            -- Add token_hash if missing
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invitations' AND column_name='token_hash'
            ) THEN
                ALTER TABLE invitations ADD COLUMN token_hash TEXT;
                -- Migrate any existing plaintext tokens: hash them or set a placeholder
                UPDATE invitations SET token_hash = token WHERE token_hash IS NULL;
                ALTER TABLE invitations ALTER COLUMN token_hash SET NOT NULL;
            END IF;

            -- Add token_hint if missing
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invitations' AND column_name='token_hint'
            ) THEN
                ALTER TABLE invitations ADD COLUMN token_hint TEXT NOT NULL DEFAULT '';
                UPDATE invitations SET token_hint = LEFT(token_hash, 8);
            END IF;
        END $$;
    """)

    # Add index on token_hint for fast lookups
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_hint ON invitations(token_hint)"
    )

    # ── role_permissions table ────────────────────────────────────────────────
    # Granular permission checks beyond coarse role guards.
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id         SERIAL PRIMARY KEY,
            role       TEXT NOT NULL,
            action     TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role, action)
        )
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rp_role_action ON role_permissions(role, action)"
    )

    # Seed default permissions
    default_permissions = [
        # Teachers
        ("teacher", "upload_material"),
        ("teacher", "post_announcement"),
        # School admins
        ("school_admin", "edit_school"),
        ("school_admin", "upload_material"),
        ("school_admin", "post_announcement"),
        ("school_admin", "view_applications"),
        # NGO officers
        ("ngo_officer", "post_scholarship"),
        ("ngo_officer", "post_announcement"),
        ("ngo_officer", "view_applications"),
    ]
    for role, action in default_permissions:
        op.execute(
            "INSERT INTO role_permissions (role, action) VALUES (%s, %s) "
            "ON CONFLICT (role, action) DO NOTHING",
            (role, action),
        )

    # ── notifications table (optional bell persistence) ───────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type       TEXT NOT NULL,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL DEFAULT '',
            read       BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notif_user_read ON notifications(user_id, read)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS role_permissions CASCADE")
    # Restore original invitations token column (cannot un-hash, just drop the new cols)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invitations' AND column_name='token_hint'
            ) THEN
                ALTER TABLE invitations DROP COLUMN token_hint;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invitations' AND column_name='token_hash'
            ) THEN
                ALTER TABLE invitations DROP COLUMN token_hash;
            END IF;
        END $$;
    """)
