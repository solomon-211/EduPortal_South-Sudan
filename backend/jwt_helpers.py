from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import jsonify, request

from settings import JWT_SECRET
from database import execute, query_all, query_one

ACCESS_TOKEN_TTL = timedelta(hours=2)
REFRESH_TOKEN_TTL = timedelta(days=30)


def parse_utc_iso(value) -> datetime | None:
    """Parse a stored ISO timestamp (SQLite text or MySQL datetime string,
    optionally 'Z'-suffixed) into a tz-aware UTC datetime, or None if it's
    missing/malformed — callers treat None as "expired" rather than crash."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def make_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def make_refresh_token(user_id: int) -> str:
    """Issue a new refresh token for user_id and store its hash. Returns the raw token."""
    raw = secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    expires_at = (datetime.now(timezone.utc) + REFRESH_TOKEN_TTL).isoformat()
    execute(
        "INSERT INTO refresh_tokens (user_id, token_hash, token_hint, expires_at) VALUES (?,?,?,?)",
        (user_id, token_hash, raw[:8], expires_at),
    )
    return raw


def _refresh_row(raw_token: str) -> dict | None:
    candidates = query_all("SELECT * FROM refresh_tokens WHERE token_hint=?", (raw_token[:8],))
    for row in candidates:
        try:
            if bcrypt.checkpw(raw_token.encode(), row["token_hash"].encode()):
                return row
        except Exception:
            continue
    return None


def verify_refresh_token(raw_token: str) -> dict | None:
    """Return the owning user if raw_token is a live, unexpired, unrevoked refresh token."""
    if not raw_token:
        return None
    row = _refresh_row(raw_token)
    if not row or row.get("revoked_at"):
        return None
    expires_at = parse_utc_iso(row.get("expires_at"))
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        return None
    user = query_one("SELECT * FROM users WHERE id=?", (row["user_id"],))
    if not user or int(user.get("verified", 0)) < 1:
        return None
    execute("UPDATE refresh_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
    return user


def revoke_refresh_token(raw_token: str) -> None:
    row = _refresh_row(raw_token) if raw_token else None
    if row:
        execute("UPDATE refresh_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))


def revoke_all_refresh_tokens(user_id: int) -> None:
    execute(
        "UPDATE refresh_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=? AND revoked_at IS NULL",
        (user_id,),
    )


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


def api_err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def log_audit(admin_id: int, action: str, target_type: str, target_id: int, note: str = "") -> None:
    execute(
        "INSERT INTO audit_log (admin_id,action,target_type,target_id,note) VALUES (?,?,?,?,?)",
        (admin_id, action, target_type, target_id, note),
    )
