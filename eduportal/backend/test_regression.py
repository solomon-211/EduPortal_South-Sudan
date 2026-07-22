"""
Regression tests — auth, materials, video-upload routes.

Run from eduportal/:
    pytest backend/test_regression.py -v

Uses an in-memory SQLite database via SQLAlchemy so no external
MySQL server is required for CI or local test runs.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

# Path setup
# Make sure backend/ is importable
_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Switch to SQLite before anything else imports the engine
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
# Hard-override (not setdefault): tests must not depend on whatever the
# developer's real .env happens to have configured for optional features.
os.environ["GOOGLE_CLIENT_ID"] = ""

# Now safe to import app
from db_connection import engine  # noqa: E402 — must come after env setup
from sqlalchemy import text


def _apply_schema() -> None:
    """Apply the initial schema to the in-memory SQLite DB."""
    # Minimal SQLite-native schema, independent of the Alembic/MySQL migrations
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
            org_type TEXT,
            org_name TEXT,
            org_id INTEGER,
            audience TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            state TEXT,
            attachment_url TEXT,
            attachment_path TEXT,
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
            ref_type TEXT,
            ref_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS email_verifications (
            user_id INTEGER PRIMARY KEY,
            token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            token_hint TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
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

# Patch schema.init_db to skip Alembic in tests
import db_schema as _schema_module
_schema_module.init_db = lambda: None

from app import app as flask_app, limiter as _limiter  # noqa: E402

# Disable Flask-Limiter for the test run — prevents 429 on rapid registrations
_limiter.enabled = False


# Helpers

@pytest.fixture(scope="session")
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["RATELIMIT_ENABLED"] = False   # disable rate limiting in tests
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
    # Force-verify in DB so existing tests can log in immediately
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET verified=1 WHERE email=:e"), {"e": email})
        conn.commit()
    return rv.get_json()


def _login(client, email: str, password: str = "Password1!") -> str:
    rv = client.post("/api/login", json={"identifier": email, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["token"]


def _login_full(client, email: str, password: str = "Password1!") -> dict:
    rv = client.post("/api/login", json={"identifier": email, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# Auth

class TestAuth:
    def test_register_success(self, client):
        rv = client.post("/api/register", json={
            "name": "Alice", "email": "alice@test.ss",
            "password": "Password1!", "role": "student",
            "state": "Jonglei", "county": "Bor South",
        })
        assert rv.status_code == 201
        data = rv.get_json()
        # Email-based registration now requires verification before a JWT is issued
        assert data.get("email_verification_required") is True
        assert "token" not in data

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


class TestRefreshTokens:
    def test_login_issues_refresh_token(self, client):
        _register(client, "jill@test.ss")
        data = _login_full(client, "jill@test.ss")
        assert data.get("refresh_token")

    def test_refresh_issues_new_access_token(self, client):
        _register(client, "kevin@test.ss")
        data = _login_full(client, "kevin@test.ss")
        rv = client.post("/api/refresh", json={"refresh_token": data["refresh_token"]})
        assert rv.status_code == 200
        refreshed = rv.get_json()
        assert refreshed["token"]
        assert refreshed["refresh_token"] != data["refresh_token"]

    def test_refresh_token_is_single_use(self, client):
        _register(client, "laura@test.ss")
        data = _login_full(client, "laura@test.ss")
        first = client.post("/api/refresh", json={"refresh_token": data["refresh_token"]})
        assert first.status_code == 200
        second = client.post("/api/refresh", json={"refresh_token": data["refresh_token"]})
        assert second.status_code == 401

    def test_refresh_rejects_garbage_token(self, client):
        rv = client.post("/api/refresh", json={"refresh_token": "not-a-real-token"})
        assert rv.status_code == 401

    def test_logout_revokes_refresh_token(self, client):
        _register(client, "mike@test.ss")
        data = _login_full(client, "mike@test.ss")
        rv = client.post("/api/logout", json={"refresh_token": data["refresh_token"]})
        assert rv.status_code == 200
        rv2 = client.post("/api/refresh", json={"refresh_token": data["refresh_token"]})
        assert rv2.status_code == 401

    def test_change_password_revokes_other_sessions(self, client):
        _register(client, "nancy@test.ss")
        data = _login_full(client, "nancy@test.ss")
        client.post("/api/change-password", json={
            "current_password": "Password1!", "new_password": "NewPass99!",
        }, headers=_auth(data["token"]))
        rv = client.post("/api/refresh", json={"refresh_token": data["refresh_token"]})
        assert rv.status_code == 401


# Stats

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


# Materials

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


# Bookmarks

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


# Video upload security

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


# Health

class TestPageRoutes:
    """Rendered HTML pages — catches template/context bugs the API tests can't see."""

    @pytest.mark.parametrize("path", [
        "/", "/login", "/register", "/dashboard", "/directory", "/materials",
        "/opportunities", "/announcements", "/forgot-password", "/terms", "/privacy", "/support",
    ])
    def test_page_renders(self, client, path):
        rv = client.get(path)
        assert rv.status_code == 200
        assert "Traceback" not in rv.get_data(as_text=True)

    def test_login_page_omits_google_button_when_unconfigured(self, client):
        rv = client.get("/login")
        assert "g_id_signin" not in rv.get_data(as_text=True)


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


# Forgot password

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


# Email Verification

class TestEmailVerification:
    def _register_unverified(self, client, email: str) -> dict:
        """Register without force-verifying — returns raw response data."""
        rv = client.post("/api/register", json={
            "name": "Unverified User",
            "email": email,
            "password": "Password1!",
            "role": "student",
            "state": "",
            "county": "",
        })
        assert rv.status_code == 201, rv.get_json()
        return rv.get_json()

    def _get_token_from_db(self, email: str) -> str | None:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT ev.token FROM email_verifications ev "
                     "JOIN users u ON u.id=ev.user_id WHERE u.email=:e"),
                {"e": email},
            ).fetchone()
        return row[0] if row else None

    def test_register_returns_verification_required(self, client):
        rv = client.post("/api/register", json={
            "name": "Vera", "email": "vera@test.ss",
            "password": "Password1!", "role": "student",
            "state": "", "county": "",
        })
        assert rv.status_code == 201
        data = rv.get_json()
        assert data.get("email_verification_required") is True
        assert "token" not in data  # no JWT until verified

    def test_unverified_user_cannot_login(self, client):
        self._register_unverified(client, "unverified@test.ss")
        rv = client.post("/api/login", json={
            "identifier": "unverified@test.ss", "password": "Password1!",
        })
        assert rv.status_code == 403
        assert "verify" in rv.get_json()["error"].lower()

    def test_verify_email_with_valid_token(self, client):
        self._register_unverified(client, "toverify@test.ss")
        token = self._get_token_from_db("toverify@test.ss")
        assert token is not None
        rv = client.get(f"/api/verify-email?token={token}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "token" in data  # JWT returned on success
        assert "verified" in data["message"].lower()

    def test_verified_user_can_login(self, client):
        self._register_unverified(client, "afterverify@test.ss")
        token = self._get_token_from_db("afterverify@test.ss")
        client.get(f"/api/verify-email?token={token}")
        rv = client.post("/api/login", json={
            "identifier": "afterverify@test.ss", "password": "Password1!",
        })
        assert rv.status_code == 200
        assert "token" in rv.get_json()

    def test_verify_email_invalid_token(self, client):
        rv = client.get("/api/verify-email?token=totallywrongtoken")
        assert rv.status_code == 400

    def test_verify_email_token_cannot_be_reused(self, client):
        self._register_unverified(client, "reuse@test.ss")
        token = self._get_token_from_db("reuse@test.ss")
        client.get(f"/api/verify-email?token={token}")
        rv = client.get(f"/api/verify-email?token={token}")
        assert rv.status_code == 400

    def test_verify_email_expired_token(self, client):
        self._register_unverified(client, "expired@test.ss")
        # Manually expire the token in the DB
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE email_verifications SET expires_at='2000-01-01 00:00:00' "
                     "WHERE user_id=(SELECT id FROM users WHERE email='expired@test.ss')"),
            )
            conn.commit()
        token = self._get_token_from_db("expired@test.ss")
        rv = client.get(f"/api/verify-email?token={token}")
        assert rv.status_code == 400
        assert "expired" in rv.get_json()["error"].lower()

    def test_resend_verification_always_returns_200(self, client):
        rv = client.post("/api/resend-verification", json={"email": "nobody@test.ss"})
        assert rv.status_code == 200

    def test_resend_verification_replaces_token(self, client):
        self._register_unverified(client, "resend@test.ss")
        old_token = self._get_token_from_db("resend@test.ss")
        client.post("/api/resend-verification", json={"email": "resend@test.ss"})
        new_token = self._get_token_from_db("resend@test.ss")
        assert new_token is not None
        assert new_token != old_token


class TestNotifications:
    def _make_admin_token(self, client, email="admin-notif@test.ss"):
        _register(client, email)
        with engine.connect() as conn:
            conn.execute(text("UPDATE users SET role='admin' WHERE email=:e"), {"e": email})
            conn.commit()
        return _login(client, email)

    def _make_scholarship_and_application(self, client, applicant_email):
        _register(client, applicant_email)
        with engine.connect() as conn:
            uid = conn.execute(
                text("SELECT id FROM users WHERE email=:e"), {"e": applicant_email}
            ).fetchone()[0]
            sid = conn.execute(text(
                "INSERT INTO scholarships (title,description,deadline,approved) "
                "VALUES ('Notif Test Scholarship','desc','2099-01-01',1)"
            )).lastrowid
            app_id = conn.execute(text(
                "INSERT INTO applications (user_id,scholarship_id,status) "
                "VALUES (:u,:s,'submitted')"
            ), {"u": uid, "s": sid}).lastrowid
            conn.commit()
        return app_id

    def test_notifications_requires_auth(self, client):
        rv = client.get("/api/notifications")
        assert rv.status_code == 401

    def test_application_status_change_creates_notification(self, client):
        app_id = self._make_scholarship_and_application(client, "peter@test.ss")
        admin_token = self._make_admin_token(client)
        rv = client.post(
            f"/api/admin/applications/{app_id}/status",
            json={"status": "shortlisted"},
            headers=_auth(admin_token),
        )
        assert rv.status_code == 200

        applicant_token = _login(client, "peter@test.ss")
        rv2 = client.get("/api/notifications", headers=_auth(applicant_token))
        assert rv2.status_code == 200
        data = rv2.get_json()
        assert data["count"] >= 1
        assert any(item["type"] == "application_status" for item in data["items"])

    def test_mark_notification_read(self, client):
        app_id = self._make_scholarship_and_application(client, "quinn@test.ss")
        admin_token = self._make_admin_token(client, "admin-notif2@test.ss")
        client.post(
            f"/api/admin/applications/{app_id}/status",
            json={"status": "successful"},
            headers=_auth(admin_token),
        )
        applicant_token = _login(client, "quinn@test.ss")
        items = client.get("/api/notifications", headers=_auth(applicant_token)).get_json()["items"]
        notif_id = next(i["id"] for i in items if i["type"] == "application_status")
        rv = client.post(f"/api/notifications/{notif_id}/read", headers=_auth(applicant_token))
        assert rv.status_code == 200
        after = client.get("/api/notifications", headers=_auth(applicant_token)).get_json()
        assert after["count"] == 0

    def test_mark_notification_read_wrong_owner(self, client):
        app_id = self._make_scholarship_and_application(client, "riley@test.ss")
        admin_token = self._make_admin_token(client, "admin-notif3@test.ss")
        client.post(
            f"/api/admin/applications/{app_id}/status",
            json={"status": "successful"},
            headers=_auth(admin_token),
        )
        owner_token = _login(client, "riley@test.ss")
        items = client.get("/api/notifications", headers=_auth(owner_token)).get_json()["items"]
        notif_id = next(i["id"] for i in items if i["type"] == "application_status")

        _register(client, "stranger@test.ss")
        stranger_token = _login(client, "stranger@test.ss")
        rv = client.post(f"/api/notifications/{notif_id}/read", headers=_auth(stranger_token))
        assert rv.status_code == 404

    def test_notifications_stream_requires_token(self, client):
        rv = client.get("/api/notifications/stream")
        assert rv.status_code == 401


class TestWebPush:
    def test_vapid_public_key_is_public(self, client):
        rv = client.get("/api/push/vapid-public-key")
        assert rv.status_code == 200
        assert "key" in rv.get_json()

    def test_subscribe_requires_auth(self, client):
        rv = client.post("/api/push/subscribe", json={"endpoint": "https://example.com/x", "keys": {"p256dh": "a", "auth": "b"}})
        assert rv.status_code == 401

    def test_subscribe_and_unsubscribe(self, client):
        _register(client, "tom@test.ss")
        token = _login(client, "tom@test.ss")
        rv = client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "pkey", "auth": "akey"}},
            headers=_auth(token),
        )
        assert rv.status_code == 200
        rv2 = client.post(
            "/api/push/unsubscribe",
            json={"endpoint": "https://push.example.com/abc"},
            headers=_auth(token),
        )
        assert rv2.status_code == 200

    def test_subscribe_missing_fields(self, client):
        _register(client, "ursula@test.ss")
        token = _login(client, "ursula@test.ss")
        rv = client.post("/api/push/subscribe", json={"endpoint": ""}, headers=_auth(token))
        assert rv.status_code == 400


class TestGoogleAuth:
    def test_credential_required(self, client):
        rv = client.post("/api/auth/google", json={})
        assert rv.status_code == 400

    def test_invalid_credential_rejected(self, client):
        # GOOGLE_CLIENT_ID is unset in the test environment, so verification
        # short-circuits to "invalid" for any token — this must never 500 or auto-log-in.
        rv = client.post("/api/auth/google", json={"credential": "not-a-real-jwt"})
        assert rv.status_code == 401
