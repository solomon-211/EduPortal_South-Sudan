import logging
from contextlib import contextmanager

from flask import g
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from config.settings import DATABASE_URL

log = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    echo=False,
)


def get_conn():
    if "db_conn" not in g:
        g.db_conn = engine.connect()
    return g.db_conn


def close_conn(exc=None):
    conn = g.pop("db_conn", None)
    if conn is None:
        return
    if exc:
        conn.rollback()
    else:
        conn.commit()
    conn.close()


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
