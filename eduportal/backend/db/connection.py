from __future__ import annotations

import logging
from contextlib import contextmanager

from flask import g
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from config.settings import DATABASE_URL

log = logging.getLogger(__name__)

# ── Engine — created once at import, shared across all requests ───────────────

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,   # drops stale connections automatically
    echo=False,
)


# ── Request-scoped connection (used by queries.py) ────────────────────────────

def get_conn():
    """Return the connection bound to the current Flask request (via g)."""
    if "db_conn" not in g:
        g.db_conn = engine.connect()
    return g.db_conn


def close_conn(exc: BaseException | None = None) -> None:
    """Commit or roll back and release the connection at end of request."""
    conn = g.pop("db_conn", None)
    if conn is None:
        return
    if exc:
        conn.rollback()
    else:
        conn.commit()
    conn.close()


# ── Standalone context manager (used outside request context: init_db, healthz) ─

@contextmanager
def get_db():
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
