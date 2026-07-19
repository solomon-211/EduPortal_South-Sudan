from __future__ import annotations

from sqlalchemy import text

from db.connection import get_conn


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    bound_sql, bound_params = _bind(sql, params)
    result = get_conn().execute(text(bound_sql), bound_params)
    return [dict(r._mapping) for r in result.fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    bound_sql, bound_params = _bind(sql, params)
    result = get_conn().execute(text(bound_sql), bound_params)
    row = result.fetchone()
    return dict(row._mapping) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    """Run an INSERT/UPDATE/DELETE. For INSERT, appends RETURNING id and returns it.

    Skips RETURNING for upserts (ON CONFLICT ... DO UPDATE) because SQLite
    does not support RETURNING on upsert statements.
    """
    sql_upper = sql.lstrip().upper()
    is_insert = sql_upper.startswith("INSERT")
    is_upsert = "ON CONFLICT" in sql_upper and "DO UPDATE" in sql_upper
    if is_insert and not is_upsert:
        base = sql.rstrip().rstrip(";")
        if "RETURNING" not in base.upper():
            base += " RETURNING id"
        bound_sql, bound_params = _bind(base, params)
        result = get_conn().execute(text(bound_sql), bound_params)
        row = result.fetchone()
        return int(row[0]) if row else 0
    bound_sql, bound_params = _bind(sql, params)
    get_conn().execute(text(bound_sql), bound_params)
    return 0


def count(sql: str, params: tuple = ()) -> int:
    r = query_one(sql, params)
    return r["count"] if r else 0


# ── Internal helper ───────────────────────────────────────────────────────────

def _bind(sql: str, params: tuple) -> tuple[str, dict]:
    """Rewrite ? placeholders to :p0, :p1 … and return (rewritten_sql, param_dict).

    All raw SQL in app.py uses ? placeholders.  SQLAlchemy text() requires
    named bindings, so we rewrite on the fly — keeping every query in app.py
    completely unchanged.
    """
    if not params:
        return sql, {}
    param_dict: dict = {}
    parts: list[str] = []
    idx = 0
    for ch in sql:
        if ch == "?":
            key = f"p{idx}"
            parts.append(f":{key}")
            param_dict[key] = params[idx]
            idx += 1
        else:
            parts.append(ch)
    return "".join(parts), param_dict
