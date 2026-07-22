from sqlalchemy import text

from db_connection import get_conn


def query_all(sql, params=()):
    bound_sql, bound_params = _bind(sql, params)
    result = get_conn().execute(text(bound_sql), bound_params)
    return [dict(r._mapping) for r in result.fetchall()]


def query_one(sql, params=()):
    bound_sql, bound_params = _bind(sql, params)
    result = get_conn().execute(text(bound_sql), bound_params)
    row = result.fetchone()
    return dict(row._mapping) if row else None


def execute(sql, params=()):
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


def count(sql, params=()):
    r = query_one(sql, params)
    return r["count"] if r else 0


def _bind(sql, params):
    if not params:
        return sql, {}
    param_dict = {}
    parts = []
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
