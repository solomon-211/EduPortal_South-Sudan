"""announcement_attachments — file upload support for announcements

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-05 00:00:00.000000
"""
from __future__ import annotations
from alembic import op

revision: str = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add attachment_path column to store uploaded file paths
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE announcements ADD COLUMN attachment_path TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE announcements DROP COLUMN attachment_path;
        EXCEPTION WHEN undefined_column THEN NULL;
        END $$;
    """)
