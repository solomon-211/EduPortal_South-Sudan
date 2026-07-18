from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager

log = logging.getLogger(__name__)

try:
    import mysql.connector as mysql_connector
except Exception:
    mysql_connector = None

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

from config.settings import (
    SQLITE_PATH,
    DATABASE_URL,
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DATABASE, POSTGRES_SSLMODE,
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE,
)

_ENGINE_OVERRIDE: str | None = None


# ── Engine detection ──────────────────────────────────────────────────────────

def _mysql_enabled() -> bool:
    return bool(MYSQL_HOST and MYSQL_DATABASE and MYSQL_USER and mysql_connector is not None)


def _postgres_enabled() -> bool:
    if psycopg is None:
        return False
    return bool(DATABASE_URL or (POSTGRES_HOST and POSTGRES_DATABASE and POSTGRES_USER))


def db_engine() -> str:
    if _ENGINE_OVERRIDE:
        return _ENGINE_OVERRIDE
    if _mysql_enabled():
        return "mysql"
    if _postgres_enabled():
        return "postgres"
    return "sqlite"


# ── SQL dialect adapters ──────────────────────────────────────────────────────

def adapt_sql(sql: str) -> str:
    engine = db_engine()
    if engine == "mysql":
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
        sql = sql.replace("INSERT OR REPLACE INTO", "REPLACE INTO")
    if engine in {"mysql", "postgres"}:
        sql = sql.replace("?", "%s")
    return sql


def adapt_schema(sql: str) -> str:
    engine = db_engine()
    if engine == "mysql":
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INT NOT NULL AUTO_INCREMENT PRIMARY KEY")
        sql = sql.replace("TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
        return sql
    if engine == "postgres":
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
    return sql


# ── DBProxy ───────────────────────────────────────────────────────────────────

class DBProxy:
    """Wraps MySQL / Postgres connections to match the sqlite3 interface."""

    def __init__(self, conn, engine: str):
        self._conn = conn
        self._engine = engine

    def execute(self, sql: str, params: tuple = ()):
        sql = adapt_sql(sql)
        if self._engine == "mysql":
            cur = self._conn.cursor(dictionary=True)
        else:
            cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(sql, params)
        return cur

    def executescript(self, script: str):
        for statement in adapt_schema(script).split(";"):
            stmt = statement.strip()
            if stmt:
                self.execute(stmt)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


# ── Connection context manager ────────────────────────────────────────────────

@contextmanager
def get_db():
    engine = db_engine()
    try:
        if engine == "postgres":
            if DATABASE_URL:
                conn = psycopg.connect(DATABASE_URL)  # type: ignore[union-attr]
            else:
                conn = psycopg.connect(  # type: ignore[union-attr]
                    host=POSTGRES_HOST, port=POSTGRES_PORT,
                    user=POSTGRES_USER, password=POSTGRES_PASSWORD,
                    dbname=POSTGRES_DATABASE, sslmode=POSTGRES_SSLMODE,
                )
            conn.autocommit = False
            db = DBProxy(conn, "postgres")
        elif engine == "mysql":
            conn = mysql_connector.connect(  # type: ignore[union-attr]
                host=MYSQL_HOST, port=MYSQL_PORT,
                user=MYSQL_USER, password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE, autocommit=False,
            )
            db = DBProxy(conn, "mysql")
        else:
            conn = sqlite3.connect(str(SQLITE_PATH))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            db = conn
    except Exception as exc:
        # Only fall back to SQLite when the configured engine is NOT postgres/mysql.
        # If postgres/mysql is explicitly configured, surface the error immediately
        # so misconfigured credentials are caught at startup, not silently ignored.
        if engine in {"postgres", "mysql"}:
            log.critical(
                "Cannot connect to %s: %s — check your .env credentials and ensure "
                "the server is running. Refusing to fall back to SQLite.",
                engine, exc,
            )
            raise
        log.warning("DB connection failed (%s), falling back to SQLite: %s", engine, exc)
        conn = sqlite3.connect(str(SQLITE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        db = conn
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Schema introspection ──────────────────────────────────────────────────────

def table_columns(db, table: str) -> set[str]:
    engine = db_engine()
    if engine == "postgres":
        cur = db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        )
        return {row["column_name"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
    if engine == "mysql":
        cur = db.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?",
            (MYSQL_DATABASE, table),
        )
        return {row["COLUMN_NAME"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
    cur = db.execute(f"PRAGMA table_info({table})")
    return {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cur.fetchall()}
