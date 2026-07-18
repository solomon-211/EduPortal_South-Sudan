from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import jsonify, request

from config.settings import JWT_SECRET
from db.queries import execute, query_one


def make_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_current_user() -> dict | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(header[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user = query_one("SELECT * FROM users WHERE id=?", (payload["sub"],))
    if not user or int(user.get("verified", 0)) < 1:
        return None
    return user


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        request.current_user = user  # type: ignore[attr-defined]
        return fn(*args, **kwargs)
    return wrapper


def require_role(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Authentication required"}), 401
            if user["role"] not in roles and user["role"] != "admin":
                return jsonify({"error": "Insufficient permissions"}), 403
            request.current_user = user  # type: ignore[attr-defined]
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_permission(action: str):
    """Check role_permissions table. admin role bypasses the table entirely."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Authentication required"}), 401
            if user["role"] != "admin":
                row = query_one(
                    "SELECT 1 FROM role_permissions WHERE role=%s AND action=%s",
                    (user["role"], action),
                )
                if not row:
                    return jsonify({"error": "Insufficient permissions"}), 403
            request.current_user = user  # type: ignore[attr-defined]
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def api_err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def log_audit(admin_id: int, action: str, target_type: str, target_id: int, note: str = "") -> None:
    execute(
        "INSERT INTO audit_log (admin_id,action,target_type,target_id,note) VALUES (?,?,?,?,?)",
        (admin_id, action, target_type, target_id, note),
    )
