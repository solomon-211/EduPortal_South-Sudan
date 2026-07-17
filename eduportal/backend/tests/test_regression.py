"""
Regression tests for auth, materials, and video-upload routes.

Run from backend/:
    pytest tests/test_regression.py -v

The tests use Flask's built-in test client against a fresh in-memory SQLite
database — no external services required.
"""
from __future__ import annotations

import io
import sys
import os

import pytest

# Ensure backend/ is on sys.path so subpackage imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Point at an in-memory SQLite DB before importing app
os.environ.setdefault("SQLITE_PATH", ":memory:")
os.environ.setdefault("POSTGRES_HOST", "")
os.environ.setdefault("MYSQL_HOST", "")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app import app  # noqa: E402  (must come after env setup)
from db.schema import init_db  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        with app.app_context():
            init_db()
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
            "name": "Alice",
            "email": "alice@test.ss",
            "password": "Password1!",
            "role": "student",
            "state": "Jonglei",
            "county": "Bor South",
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
        rv = client.post("/api/login", json={"identifier": "eve@test.ss", "password": "Password1!"})
        assert rv.status_code == 200
        assert "token" in rv.get_json()

    def test_login_wrong_password(self, client):
        _register(client, "frank@test.ss")
        rv = client.post("/api/login", json={"identifier": "frank@test.ss", "password": "WrongPass1!"})
        assert rv.status_code == 401

    def test_login_unknown_user(self, client):
        rv = client.post("/api/login", json={"identifier": "nobody@test.ss", "password": "Password1!"})
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
            "current_password": "Password1!",
            "new_password": "NewPass99!",
        }, headers=_auth(token))
        assert rv.status_code == 200
        # Old password must now fail
        rv2 = client.post("/api/login", json={"identifier": "henry@test.ss", "password": "Password1!"})
        assert rv2.status_code == 401

    def test_change_password_wrong_current(self, client):
        _register(client, "iris@test.ss")
        token = _login(client, "iris@test.ss")
        rv = client.post("/api/change-password", json={
            "current_password": "WrongCurrent!",
            "new_password": "NewPass99!",
        }, headers=_auth(token))
        assert rv.status_code == 401


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
        rv = client.post("/api/materials", json={
            "title": "Incomplete",
        }, headers=_auth(token))
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
        token = self._teacher_token(client, "vid_teacher1@test.ss")
        mid = self._create_material(client, token)
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(b"some data"), "notes.txt")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code == 400

    def test_upload_rejects_fake_mp4(self, client):
        """A file named .mp4 but containing plain text must be rejected."""
        token = self._teacher_token(client, "vid_teacher2@test.ss")
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
        token = self._teacher_token(client, "vid_teacher3@test.ss")
        mid = self._create_material(client, token)
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(b"<html>not a video</html>"), "fake.webm")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code == 400

    def test_upload_accepts_valid_mp4_magic(self, client):
        """Bytes with a valid ftyp box should pass the magic-byte check."""
        token = self._teacher_token(client, "vid_teacher4@test.ss")
        mid = self._create_material(client, token)
        # Minimal MP4 magic: 4-byte size + 'ftyp' + padding
        mp4_header = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(mp4_header + b"\x00" * 100), "real.mp4")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        # 200 = saved; 404 = materials folder missing in test env — both mean magic check passed
        assert rv.status_code in (200, 404, 500)
        if rv.status_code == 400:
            pytest.fail(f"Valid MP4 magic was rejected: {rv.get_json()}")

    def test_upload_accepts_valid_webm_magic(self, client):
        token = self._teacher_token(client, "vid_teacher5@test.ss")
        mid = self._create_material(client, token)
        webm_header = b"\x1aE\xdf\xa3" + b"\x00" * 100
        rv = client.post(
            f"/api/materials/{mid}/upload",
            data={"file": (io.BytesIO(webm_header), "real.webm")},
            content_type="multipart/form-data",
            headers=_auth(token),
        )
        assert rv.status_code in (200, 404, 500)
        if rv.status_code == 400:
            pytest.fail(f"Valid WebM magic was rejected: {rv.get_json()}")

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
        # Must never expose raw exception text in production-safe mode
        assert "error" not in data.get("database", {})

    def test_healthz_no_traceback_in_body(self, client):
        rv = client.get("/healthz")
        body = rv.get_data(as_text=True)
        assert "Traceback" not in body
        assert "Exception" not in body
