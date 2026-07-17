from __future__ import annotations

from db.connection import get_db, db_engine


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with get_db() as db:
        row = db.execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    with get_db() as db:
        cur = db.execute(sql, params)
        if db_engine() == "postgres" and sql.lstrip().upper().startswith("INSERT"):
            try:
                row = db.execute("SELECT LASTVAL() AS last_id").fetchone()
                if row:
                    return int(row["last_id"] if isinstance(row, dict) else row[0])
            except Exception:
                return 0
        return cur.lastrowid or 0


def count(sql: str, params: tuple = ()) -> int:
    r = query_one(sql, params)
    return r["count"] if r else 0
