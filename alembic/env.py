"""Alembic environment — reads the same .env used by the Flask app."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make backend/ importable so settings resolves
_HERE = Path(__file__).resolve().parent          # alembic/
_ROOT = _HERE.parent                             # eduportal/
_BACKEND = _ROOT / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# Build the database URL (MySQL in production, SQLite for local dev/test)

def _db_url() -> str:
    from settings import DATABASE_URL
    return DATABASE_URL


# Alembic Config
config = context.config
config.set_main_option("sqlalchemy.url", _db_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No declarative metadata — we manage schema via raw SQL migrations.
target_metadata = None


# Migration runners

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
