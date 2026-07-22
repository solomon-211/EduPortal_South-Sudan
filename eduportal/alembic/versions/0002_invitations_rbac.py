"""Fix invitations schema and add role_permissions + notifications tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-18

This migration is dialect-aware across MySQL and SQLite:
- Column existence is checked via SQLAlchemy's inspector (works on both)
  rather than native ADD COLUMN IF NOT EXISTS, which MySQL doesn't support.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _col_exists(table: str, col: str) -> bool:
    """Return True if *col* already exists in *table*."""
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


def _add_col_safe(table: str, col: str, coltype) -> None:
    """Add a column only if it doesn't already exist (works on both MySQL and SQLite)."""
    if not _col_exists(table, col):
        op.add_column(table, sa.Column(col, coltype))


def upgrade() -> None:
    bind = op.get_bind()
    pk = "INT AUTO_INCREMENT PRIMARY KEY" if bind.dialect.name == "mysql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # Fix invitations table
    _add_col_safe("invitations", "token_hash", sa.Text())
    _add_col_safe("invitations", "token_hint", sa.String(16))

    # Migrate any existing plaintext tokens into token_hash (plain copy for now)
    op.execute(sa.text(
        "UPDATE invitations SET token_hash = token WHERE token_hash IS NULL AND token IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE invitations SET token_hint = SUBSTR(COALESCE(token_hash,''),1,8) WHERE token_hint IS NULL OR token_hint = ''"
    ))

    # Index on token_hint
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_invitations_hint ON invitations(token_hint)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_invitations_hint ON invitations(token_hint)"))

    # role_permissions
    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id         {pk},
            role       VARCHAR(50) NOT NULL,
            action     VARCHAR(50) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role, action)
        )
    """))

    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_rp_role_action ON role_permissions(role, action)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_rp_role_action ON role_permissions(role, action)"))

    # Seed default permissions
    perms = [
        ("teacher",      "upload_material"),
        ("teacher",      "post_announcement"),
        ("school_admin", "edit_school"),
        ("school_admin", "upload_material"),
        ("school_admin", "post_announcement"),
        ("school_admin", "view_applications"),
        ("ngo_officer",  "post_scholarship"),
        ("ngo_officer",  "post_announcement"),
        ("ngo_officer",  "view_applications"),
    ]
    upsert_sql = (
        "INSERT IGNORE INTO role_permissions (role, action) VALUES (:r, :a)"
        if bind.dialect.name == "mysql"
        else "INSERT INTO role_permissions (role, action) VALUES (:r, :a) ON CONFLICT DO NOTHING"
    )
    for role, action in perms:
        op.execute(sa.text(upsert_sql).bindparams(r=role, a=action))

    # notifications
    op.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS notifications (
            id         {pk},
            user_id    INTEGER NOT NULL,
            type       VARCHAR(50) NOT NULL,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            `read`     INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    if bind.dialect.name == "mysql":
        op.execute(sa.text("CREATE INDEX idx_notif_user_read ON notifications(user_id, `read`)"))
    else:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_notif_user_read ON notifications(user_id, `read`)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS notifications"))
    op.execute(sa.text("DROP TABLE IF EXISTS role_permissions"))
    bind = op.get_bind()
    # SQLite's DROP COLUMN support is unreliable across versions — skip there.
    if bind.dialect.name != "sqlite":
        if _col_exists("invitations", "token_hint"):
            op.drop_column("invitations", "token_hint")
        if _col_exists("invitations", "token_hash"):
            op.drop_column("invitations", "token_hash")
