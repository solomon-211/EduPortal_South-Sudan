"""Alembic environment — reads the same .env used by the Flask app."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make backend/ importable so config.settings resolves ─────────────────────
_HERE = Path(__file__).resolve().parent          # alembic/
_ROOT = _HERE.parent                             # eduportal/
_BACKEND = _ROOT / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# ── Build the PostgreSQL URL from env vars ────────────────────────────────────

def _pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # SQLAlchemy requires postgresql:// not postgres://
        return url.replace("postgres://", "postgresql://", 1)
    host     = os.environ.get("POSTGRES_HOST", "localhost")
    port     = os.environ.get("POSTGRES_PORT", "5432")
    user     = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    dbname   = os.environ.get("POSTGRES_DATABASE", "")
    sslmode  = os.environ.get("POSTGRES_SSLMODE", "prefer")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"


# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config
config.set_main_option("sqlalchemy.url", _pg_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No declarative metadata — we manage schema via raw SQL migrations.
target_metadata = None


# ── Migration runners ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
