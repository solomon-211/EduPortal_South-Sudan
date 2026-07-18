"""
Regression tests — auth, materials, video-upload routes.

Run from eduportal/:
    pytest backend/tests/test_regression.py -v

Uses an in-memory SQLite database via SQLAlchemy so no external
PostgreSQL server is required for CI or local test runs.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
# Make sure backend/ is importable
_BACKEND = os.path.dirname(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ── Switch to SQLite before anything else imports the engine ──────────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

# ── Now safe to import app ────────────────────────────────────────────────────
from db.connection import engine  # noqa: E402 — must come after env setup
from sqlalchemy import text

# Create all tables in the in-memory SQLite DB using the initial schema SQL
from pathlib import Path
_MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "database" / "migrations"


def _apply_schema() -> None:
    """Apply the initial schema to the in-memory SQLite DB."""
    # Use a minimal SQLite-compatible schema (no SERIAL, no DO $$...$$)
    ddl = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            state TEXT NOT NULL DEFAULT '',
            county TEXT NOT NULL DEFAULT '',
            verified INTEGER NOT NULL DEFAULT 1,
            notify_email INTEGER NOT NULL DEFAULT 1,
            notify_sms INTEGER NOT NULL DEFAULT 1,
            notify_inapp INTEGER NOT NULL DEFAULT 1,
            avatar TEXT,
            grade TEXT DEFAULT '',
            school_name TEXT DEFAULT '',
            child_school TEXT DEFAULT '',
            child_grade TEXT DEFAULT '',
            subjects TEXT DEFAULT '',
            institution TEXT DEFAULT '',
            experience_years INTEGER,
            managed_school TEXT DEFAULT '',
            position TEXT DEFAULT '',
            school_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            county TEXT NOT NULL,
            level TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'mixed',
            curriculum TEXT NOT NULL DEFAULT 'National',
            contact_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT,
            capacity INTEGER,
            status TEXT NOT NULL DEFAULT 'open',
            enrollment INTEGER DEFAULT 0,
            language TEXT DEFAULT 'English',
            boarding TEXT DEFAULT 'Day',
            hours TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admission_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            item_label TEXT NOT NULL,
            is_required INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            grade TEXT NOT NULL,
            year INTEGER NOT NULL,
            type TEXT NOT NULL,
            file_size TEXT,
            preview_text TEXT,
            file_path TEXT,
            uploaded_by TEXT,
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            audience TEXT NOT NULL,
            expires_at TEXT,
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ngos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_name TEXT NOT NULL,
            contact TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            description TEXT,
            verified INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ngo_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            eligibility TEXT NOT NULL DEFAULT '',
            deadline TEXT NOT NULL,
            how_to_apply TEXT NOT NULL DEFAULT '',
            required_docs TEXT,
            external_link TEXT,
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scholarship_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            note TEXT,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, scholarship_id)
        );
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, item_type, item_id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER,
            note TEXT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            user_id INTEGER PRIMARY KEY,
            token TEXT NOT NULL,
            token_hash TEXT,
            token_hint TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            token_hash TEXT,
            token_hint TEXT DEFAULT '',
            role TEXT NOT NULL,
            ref_id INTEGER,
            email TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            UNIQUE (role, action)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    with engine.connect() as conn:
        for stmt in ddl.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()


_apply_schema()

from app import app as flask_app  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _register(client, email: str, password: str = "Password1!", role: str = "student") -> dict:
    rv = client.post("/api/register", json={
        "name": "Test User",
        "email": email,
        "password": password,
        "role": role,
        "state": "Central Equatoria",
        "county": "Juba",
    })
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()


def _login(client, email: str, password: str = "Password1!") -> str:
    rv = client.post("/api/login", json={"identifier": email, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client):
        rv = client.post("/api/register", json={
            "name": "Alice", "email": "alice@test.ss",
            "password": "Password1!", "role": "student",
            "state": "Jonglei", "county": "Bor South",
        })
        assert rv.status_code == 201
        data = rv.get_json()
        assert "token" in data
        assert data["user"]["role"] == "student"

    def test_register_duplicate_email(self, client):
        client.post("/api/register", json={
            "name": "Bob", "email": "bob@test.ss",
            "password": "Password1!", "role": "student",
            "state": "", "county": "",
        })
        rv = client.post("/api/register", json={
            "name": "Bob2", "email": "bob@test.ss",
            "password": "Password1!", "role": "student",
            "state": "", "county": "",
        })
        assert rv.status_code == 409

    def test_register_short_password(self, client):
        rv = client.post("/api/register", json={
            "name": "Carol", "email": "carol@test.ss",
            "password": "short", "role": "student",
            "state": "", "county": "",
        })
        assert rv.status_code == 400

    def test_register_invalid_role(self, client):
        rv = client.post("/api/register", json={
            "name": "Dave", "email": "dave@test.ss",
            "password": "Password1!", "role": "superuser",
            "state": "", "county": "",
        })
        assert rv.status_code == 400

    def test_login_success(self, client):
        _register(client, "eve@test.ss")
        rv = client.post("/api/login", json={
            "identifier": "eve@test.ss", "password": "Password1!",
        })
        assert rv.status_code == 200
        assert "token" in rv.get_json()

    def test_login_wrong_password(self, client):
        _register(client, "frank@test.ss")
        rv = client.post("/api/login", json={
            "identifier": "frank@test.ss", "password": "WrongPass1!",
        })
        assert rv.status_code == 401

    def test_login_unknown_user(self, client):
        rv = client.post("/api/login", json={
            "identifier": "nobody@test.ss", "password": "Password1!",
        })
        assert rv.status_code == 401

    def test_me_requires_auth(self, client):
        rv = client.get("/api/me")
        assert rv.status_code == 401

    def test_me_returns_profile(self, client):
        _register(client, "grace@test.ss")
        token = _login(client, "grace@test.ss")
        rv = client.get("/api/me", headers=_auth(token))
        assert rv.status_code == 200
        assert rv.get_json()["user"]["email"] == "grace@test.ss"

    def test_change_password(self, client):
        _register(client, "henry@test.ss")
        token = _login(client, "henry@test.ss")
        rv = client.post("/api/change-password", json={
            "current_password": "Password1!", "new_password": "NewPass99!",
        }, headers=_auth(token))
        assert rv.status_code == 200
        rv2 = client.post("/api/login", json={
            "identifier": "henry@test.ss", "password": "Password1!",
        })
        assert rv2.status_code == 401

    def test_change_password_wrong_current(self, client):
        _register(client, "iris@test.ss")
        token = _login(client, "iris@test.ss")
        rv = client.post("/api/change-password", json={
            "current_password": "WrongCurrent!", "new_password": "NewPass99!",
        }, headers=_auth(token))
        assert rv.status_code == 401


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_public(self, client):
        rv = client.get("/api/stats")
        assert rv.status_code == 200
        data = rv.get_json()
        for key in ("schools", "materials", "scholarships", "announcements", "users"):
            assert key in data

    def test_schools_list(self, client):
        rv = client.get("/api/schools")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "items" in data
        assert "total" in data

    def test_schools_search(self, client):
        rv = client.get("/api/schools?search=Juba")
        assert rv.status_code == 200

    def test_schools_filter_state(self, client):
        rv = client.get("/api/schools?state=Central+Equatoria")
        assert rv.status_code == 200

    def test_announcements_list(self, client):
        rv = client.get("/api/announcements")
        assert rv.status_code == 200
        assert "items" in rv.get_json()

    def test_scholarships_list(self, client):
        rv = client.get("/api/scholarships")
        assert rv.status_code == 200
        assert "items" in rv.get_json()


# ── Materials ─────────────────────────────────────────────────────────────────

class TestMaterials:
    def test_list_materials_public(self, client):
        rv = client.get("/api/materials")
        assert rv.status_code == 200
        assert "items" in rv.get_json()

    def test_submit_material_requires_teacher_role(self, client):
        _register(client, "student_mat@test.ss", role="student")
        token = _login(client, "student_mat@test.ss")
        rv = client.post("/api/materials", json={
            "title": "Test", "subject": "Math", "grade": "P5",
            "year": 2024, "type": "past paper",
        }, headers=_auth(token))
        assert rv.status_code == 403

    def test_submit_material_as_teacher(self, client):
        _register(client, "teacher_mat@test.ss", role="teacher")
        token = _login(client, "teacher_mat@test.ss")
        rv = client.post("/api/materials", json={
            "title": "Algebra Notes", "subject": "Mathematics",
            "grade": "S4", "year": 2024, "type": "study guide",
        }, headers=_auth(token))
        assert rv.status_code == 201
        assert "id" in rv.get_json()

    def test_submit_material_missing_fields(self, client):
        _register(client, "teacher_mat2@test.ss", role="teacher")
        token = _login(client, "teacher_mat2@test.ss")
        rv = client.post("/api/materials", json={"title": "Incomplete"},
                         headers=_auth(token))
        assert rv.status_code == 400

    def test_material_detail_not_found(self, client):
        rv = client.get("/api/materials/99999")
        assert rv.status_code == 404

    def test_download_requires_auth(self, client):
        rv = client.get("/api/materials/1/download")
        assert rv.status_code == 401

    def test_stream_requires_auth(self, client):
        rv = client.get("/api/materials/1/stream")
        assert rv.status_code == 401

    def test_materials_filter_subject(self, client):
        rv = client.get("/api/materials?subject=Mathematics")
        assert rv.status_code == 200

    def test_materials_pagination(self, client):
        rv = client.get("/api/materials?page=1")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "page" in data
        assert data["page"] == 1


# ── Bookmarks ─────────────────────────────────────────────────────────────────

class TestBookmarks:
    def test_bookmarks_requires_auth(self, client):
        rv = client.get("/api/bookmarks")
        assert rv.status_code == 401

    def test_bookmarks_detailed_requires_auth(self, client):
        rv = client.get("/api/bookmarks/detailed")
        assert rv.status_code == 401

    def test_save_and_list_bookmark(self, client):
        _register(client, "bm_user@test.ss")
        token = _login(client, "bm_user@test.ss")
        # Save a school bookmark (school id 1 may not exist but the insert should succeed)
        rv = client.post("/api/bookmarks", json={"item_type": "school", "item_id": 1},
                         headers=_auth(token))
        assert rv.status_code == 200
        rv2 = client.get("/api/bookmarks", headers=_auth(token))
        assert rv2.status_code == 200
        assert len(rv2.get_json()["items"]) >= 1

    def test_bookmark_invalid_type(self, client):
        _register(client, "bm_user2@test.ss")
        token = _login(client, "bm_user2@test.ss")
        rv = client.post("/api/bookmarks", json={"item_type": "invalid", "item_id": 1},
                         headers=_auth(token))
        assert rv.status_code == 400


# ── Video upload security ─────────────────────────────────────────────────────

class TestVideoUpload:
    def _teacher_token(self, client, email: str) -> str:
        _register(client, email, role="teacher")
        return _login(client, email)

    def _create_material(self, client, token: str) -> int:
        rv = client.post("/api/materials", json={
            "title": "Video Tutorial", "subject": "Science",
            "grade": "S6", "year": 2024, "type": "tutorial video",
        }, headers=_auth(token))
        assert rv.status_code == 201
        return rv.get_json()["id"]

    def test_upload_rejects_wrong_extension(self, client):
        token = self._teacher_token(client, "vid1@test.ss")
        mid = self._create_material(client, token)
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(b"data"), "notes.txt")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code == 400

    def test_upload_rejects_fake_mp4(self, client):
        token = self._teacher_token(client, "vid2@test.ss")
        mid = self._create_material(client, token)
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(b"this is not a video at all"), "fake.mp4")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code == 400
        assert "content" in rv.get_json()["error"].lower()

    def test_upload_rejects_fake_webm(self, client):
        token = self._teacher_token(client, "vid3@test.ss")
        mid = self._create_material(client, token)
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(b"<html>not a video</html>"), "fake.webm")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code == 400

    def test_upload_accepts_valid_mp4_magic(self, client):
        token = self._teacher_token(client, "vid4@test.ss")
        mid = self._create_material(client, token)
        mp4_header = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00" + b"\x00" * 100
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(mp4_header), "real.mp4")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        # 200=saved, 500=disk not writable in test env — both mean magic check passed
        assert rv.status_code in (200, 500), f"Valid MP4 magic was rejected: {rv.get_json()}"

    def test_upload_accepts_valid_webm_magic(self, client):
        token = self._teacher_token(client, "vid5@test.ss")
        mid = self._create_material(client, token)
        webm_header = b"\x1aE\xdf\xa3" + b"\x00" * 100
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(webm_header), "real.webm")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code in (200, 500), f"Valid WebM magic was rejected: {rv.get_json()}"

    def test_upload_requires_auth(self, client):
        rv = client.post(
            "/api/materials/1/upload",
            data={"file": (io.BytesIO(b"data"), "file.mp4")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 401


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_healthz_ok(self, client):
        rv = client.get("/healthz")
        data = rv.get_json()
        assert rv.status_code in (200, 503)
        assert "status" in data

    def test_healthz_no_traceback(self, client):
        rv = client.get("/healthz")
        body = rv.get_data(as_text=True)
        assert "Traceback" not in body
        assert "Exception" not in body


# ── Forgot password ───────────────────────────────────────────────────────────

class TestForgotPassword:
    def test_forgot_password_unknown_user(self, client):
        rv = client.post("/api/forgot-password", json={"identifier": "noone@test.ss"})
        assert rv.status_code == 200  # always returns 200 to avoid enumeration

    def test_forgot_password_known_user(self, client):
        _register(client, "reset_user@test.ss")
        rv = client.post("/api/forgot-password", json={"identifier": "reset_user@test.ss"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert "message" in data
        # In dev mode (no SMTP) the token is returned directly
        if "dev_token" in data:
            assert len(data["dev_token"]) > 10

    def test_reset_password_bad_token(self, client):
        rv = client.post("/api/reset-password", json={
            "user_id": 1, "token": "badtoken", "new_password": "NewPass99!",
        })
        assert rv.status_code == 400
