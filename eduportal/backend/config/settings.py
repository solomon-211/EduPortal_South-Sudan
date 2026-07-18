from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR         = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

FRONTEND_DIR     = BASE_DIR / "frontend"
HTML_DIR         = FRONTEND_DIR / "html"
CSS_DIR          = FRONTEND_DIR / "css"
JS_DIR           = FRONTEND_DIR / "javascript"
ASSETS_DIR       = FRONTEND_DIR / "assets"
MIGRATIONS_DIR   = BASE_DIR / "database" / "migrations"

# ── Upload limits ─────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS    = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_MATERIAL_EXTS = {"pdf", "mp4", "webm", "ogg", "m4v"}
MAX_AVATAR_BYTES      = 2 * 1024 * 1024    # 2 MB
MAX_MATERIAL_BYTES    = 100 * 1024 * 1024  # 100 MB

UPLOAD_FOLDER    = ASSETS_DIR / "avatars"
MATERIALS_FOLDER = ASSETS_DIR / "materials"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# Prefer a full DATABASE_URL; fall back to building one from individual vars.

def _build_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # SQLAlchemy requires postgresql:// not postgres://
        return url.replace("postgres://", "postgresql://", 1)
    host     = os.environ.get("POSTGRES_HOST", "localhost").strip()
    port     = os.environ.get("POSTGRES_PORT", "5432").strip()
    user     = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    dbname   = os.environ.get("POSTGRES_DATABASE", "").strip()
    sslmode  = (os.environ.get("POSTGRES_SSLMODE", "prefer").strip() or "prefer")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"

DATABASE_URL = _build_database_url()

# ── Auth ──────────────────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-in-prod")

# ── SMTP ──────────────────────────────────────────────────────────────────────

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@eduportal.ss")

# ── Africa's Talking (SMS) ────────────────────────────────────────────────────

AT_API_KEY   = os.environ.get("AT_API_KEY", "")
AT_SENDER_ID = os.environ.get("AT_SENDER_ID", "EduPortal")
