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
DB_DIR           = BASE_DIR / "database"
SQLITE_PATH      = DB_DIR / "eduportal.sqlite3"
UPLOAD_FOLDER    = ASSETS_DIR / "avatars"
MATERIALS_FOLDER = ASSETS_DIR / "materials"
MIGRATIONS_DIR   = DB_DIR / "migrations"

# ── Upload limits ─────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS    = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_MATERIAL_EXTS = {"pdf"}
MAX_AVATAR_BYTES      = 2 * 1024 * 1024   # 2 MB
MAX_MATERIAL_BYTES    = 20 * 1024 * 1024  # 20 MB

# ── PostgreSQL ────────────────────────────────────────────────────────────────

DATABASE_URL      = os.environ.get("DATABASE_URL", "").strip()
POSTGRES_HOST     = os.environ.get("POSTGRES_HOST", "").strip()
POSTGRES_PORT     = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER     = os.environ.get("POSTGRES_USER", "").strip()
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "").strip()
POSTGRES_SSLMODE  = os.environ.get("POSTGRES_SSLMODE", "prefer").strip() or "prefer"

# ── MySQL ─────────────────────────────────────────────────────────────────────

MYSQL_HOST     = os.environ.get("MYSQL_HOST", "").strip()
MYSQL_PORT     = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER     = os.environ.get("MYSQL_USER", "").strip()
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "").strip()

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
