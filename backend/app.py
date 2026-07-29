from __future__ import annotations

import io
import logging
import os
import mimetypes
import secrets
from datetime import datetime, timedelta, timezone
from queue import Empty

import bcrypt
import jwt
from flask import Flask, jsonify, render_template, request, redirect, url_for, Response, send_file as flask_send_file, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename

log = logging.getLogger(__name__)

from google_oauth import verify_google_token
from jwt_helpers import (
    api_err, get_current_user, log_audit, make_refresh_token, make_token,
    parse_utc_iso, require_auth, require_role, revoke_all_refresh_tokens,
    revoke_refresh_token, verify_refresh_token,
)
from settings import (
    ASSETS_DIR, CSS_DIR, HTML_DIR, JS_DIR, MAX_MATERIAL_BYTES, MAX_AVATAR_BYTES,
    ALLOWED_EXTENSIONS, ALLOWED_MATERIAL_EXTS, UPLOAD_FOLDER, MATERIALS_FOLDER,
    ANNOUNCEMENTS_FOLDER, LOGOS_FOLDER, REQUIREMENTS_FOLDER, SCHOLARSHIPS_FOLDER,
    VAPID_PUBLIC_KEY, GOOGLE_CLIENT_ID, JWT_SECRET,
)
from database import close_conn, count, execute, get_db, init_db, is_mysql, query_all, query_one, engine as db_engine
from notification import (
    create_notification, push_is_configured, send_email, send_sms,
    send_verification_email, subscribe, unsubscribe,
)
from storage import save_file, public_url as storage_url, using_s3

_DB_READY = False

if JWT_SECRET == "dev-jwt-secret-change-in-prod" and os.environ.get("FLASK_DEBUG", "false").lower() != "true":
    log.warning(
        "JWT_SECRET_KEY is not set — using the publicly-known dev default. "
        "Every auth token is forgeable. Set JWT_SECRET_KEY in .env before deploying."
    )

VIDEO_EXTENSIONS = {"mp4", "webm", "ogg", "m4v"}

# Magic-byte signatures for allowed video containers
_VIDEO_MAGIC: list[tuple[bytes, int]] = [
    (b"\x00\x00\x00", 0),          # MP4 / M4V  (ftyp box — first 3 bytes are \x00\x00\x00)
    (b"\x1aE\xdf\xa3", 0),         # WebM / MKV EBML header
    (b"OggS", 0),                   # OGG
]


def _is_valid_video(stream) -> bool:
    """Read the first 12 bytes and check against known video magic bytes."""
    header = stream.read(12)
    stream.seek(0)
    # MP4/M4V: bytes 4-7 are 'ftyp'
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return True
    for magic, offset in _VIDEO_MAGIC:
        if header[offset:offset + len(magic)] == magic:
            return True
    return False


def _is_valid_pdf(stream) -> bool:
    """A real PDF starts with the literal bytes %PDF- — cheap and reliable to check."""
    header = stream.read(5)
    stream.seek(0)
    return header == b"%PDF-"


def _generate_pdf_thumbnail(pdf_bytes: bytes) -> bytes | None:
    """Render the first page of a PDF to a JPEG thumbnail. A failure here
    (corrupt PDF, PyMuPDF missing) should never block the upload itself —
    the card just falls back to the generic document icon."""
    try:
        import fitz  # PyMuPDF
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            pixmap = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
            return pixmap.tobytes("jpeg")
    except Exception:
        log.exception("PDF thumbnail generation failed")
        return None


def _generate_video_thumbnail(video_bytes: bytes, ext: str) -> bytes | None:
    """Extract a frame ~1s into the video as a JPEG thumbnail via the
    system ffmpeg binary. Returns None (never raises) if ffmpeg isn't
    installed or extraction fails for any reason — same reasoning as the
    PDF path above, a missing thumbnail isn't worth failing the upload."""
    import subprocess
    import tempfile
    src_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as src:
            src.write(video_bytes)
            src_path = src.name
        out_path = src_path + "_thumb.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:01", "-i", src_path,
             "-vframes", "1", "-vf", "scale=320:-1", out_path],
            capture_output=True, timeout=20, check=True,
        )
        with open(out_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        log.warning("ffmpeg not installed — skipping video thumbnail generation")
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log.exception("Video thumbnail generation failed")
        return None
    finally:
        for p in (src_path, out_path):
            if p and os.path.exists(p):
                os.remove(p)


# Magic-byte signatures for allowed avatar image formats
_IMAGE_MAGIC: list[tuple[bytes, int]] = [
    (b"\xff\xd8\xff", 0),                # JPEG
    (b"\x89PNG\r\n\x1a\n", 0),           # PNG
    (b"GIF87a", 0),                      # GIF (87a)
    (b"GIF89a", 0),                      # GIF (89a)
]


def _is_valid_image(stream) -> bool:
    """Check the first 12 bytes against known JPEG/PNG/GIF/WEBP magic bytes."""
    header = stream.read(12)
    stream.seek(0)
    if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True
    for magic, offset in _IMAGE_MAGIC:
        if header[offset:offset + len(magic)] == magic:
            return True
    return False


def _read_uploaded_image(file, max_bytes: int) -> tuple[str, bytes]:
    """Validate an uploaded image (extension, magic bytes, size); return (ext, data) or raise ValueError."""
    if not file.filename:
        raise ValueError("Empty filename")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only JPG, PNG, GIF, or WEBP files are allowed")
    if not _is_valid_image(file.stream):
        raise ValueError("File content does not match a recognised image format")
    data = file.stream.read()
    if len(data) > max_bytes:
        raise ValueError(f"File must be under {max_bytes // (1024 * 1024)} MB")
    return ext, data


def _material_kind_from_path(file_path: str | None) -> str:
    if not file_path:
        return "file"
    extension = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if extension in VIDEO_EXTENSIONS:
        return "video"
    return "file"


def _material_mimetype(file_path: str | None) -> str:
    if not file_path:
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(file_path)
    return guessed or ("video/mp4" if _material_kind_from_path(file_path) == "video" else "application/octet-stream")


def _build_update_clause(data: dict, allowed_fields: list[str], transform=None) -> tuple[list[str], list]:
    """Build the `sets`/`params` pair for an `UPDATE ... SET {sets}` clause
    from whichever of `allowed_fields` are present in `data`. Pass
    `transform` to normalise each value (e.g. strip a string) before it's
    added to `params`. Fields absent from `data` are left untouched, so a
    caller can PATCH just the fields it sends without clobbering the rest."""
    sets: list[str] = []
    params: list = []
    for field in allowed_fields:
        if field in data:
            value = transform(data[field]) if transform else data[field]
            sets.append(f"{field}=?")
            params.append(value)
    return sets, params


def _append_equals_filters(sql: str, params: list, pairs: list[tuple[str, str]]) -> str:
    """Append ` AND {column}=?` to `sql` for each (value, column) in `pairs`
    where value is truthy, appending value to `params`. Covers only simple
    exact-match filters — LIKE/range/OR/type-cast conditions stay inline at
    the call site rather than being forced through a one-size-fits-all shape.
    Assumes `sql` already has a WHERE clause to AND onto."""
    for value, column in pairs:
        if value:
            sql += f" AND {column}=?"
            params.append(value)
    return sql


def _public_file_url(stored_key: str, folder_name: str, filename: str) -> str:
    """Resolve a just-saved upload to its publicly reachable URL — S3/Supabase
    when configured, otherwise the local /static/<folder_name>/<filename> path."""
    return storage_url(stored_key) if using_s3() else f"/static/{folder_name}/{filename}"

app = Flask(
    __name__,
    template_folder=str(HTML_DIR),
    static_folder=None,
)
app.config["MAX_CONTENT_LENGTH"] = MAX_MATERIAL_BYTES

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

@app.teardown_appcontext
def teardown_db(exc: BaseException | None) -> None:
    close_conn(exc)

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # JS/CSS have no cache-busting query string, so without this a browser can
    # keep serving a pre-fix copy indefinitely after a deploy. no-cache still
    # allows a fast 304 revalidation — it just stops the browser from skipping
    # that check entirely.
    if request.path == "/sw.js" or (request.path.startswith("/static/") and request.path.endswith((".js", ".css"))):
        response.headers["Cache-Control"] = "no-cache"
    # API responses are per-user and change on every write (approval queue,
    # notifications, etc.) — without this, a browser or an in-between proxy/CDN
    # can serve a stale JSON response and the new data only appears after a
    # hard refresh forces a cache bypass.
    elif request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/sw.js")
def service_worker():
    # Served from the root path (not /static/) so its default scope covers the whole site
    return send_from_directory(str(JS_DIR), "sw.js", mimetype="text/javascript")

@app.route("/favicon.svg")
@app.route("/favicon.ico")
def favicon():
    # Same SVG for both — every browser that still requests /favicon.ico
    # directly (rather than honoring <link rel="icon">) accepts an SVG body.
    return send_from_directory(str(ASSETS_DIR), "favicon.svg", mimetype="image/svg+xml")

@app.route("/static/<path:filename>")
def static_files(filename: str):
    # CSS compatibility
    if filename.startswith("html/"):
        return send_from_directory(str(CSS_DIR / "html"), filename[len("html/"):])

    # JavaScript modules
    if filename.startswith("app/"):
        return send_from_directory(str(JS_DIR / "app"), filename[len("app/"):])
    if filename.startswith("navigation/"):
        return send_from_directory(str(JS_DIR / "navigation"), filename[len("navigation/"):])

    # Uploaded and generated assets
    if filename.startswith("avatars/"):
        return send_from_directory(str(ASSETS_DIR / "avatars"), filename[len("avatars/"):])
    if filename.startswith("materials/"):
        return send_from_directory(str(ASSETS_DIR / "materials"), filename[len("materials/"):])
    if filename.startswith("announcements/"):
        return send_from_directory(str(ASSETS_DIR / "announcements"), filename[len("announcements/"):])
    if filename.startswith("logos/"):
        return send_from_directory(str(ASSETS_DIR / "logos"), filename[len("logos/"):])
    if filename.startswith("requirements/"):
        return send_from_directory(str(ASSETS_DIR / "requirements"), filename[len("requirements/"):])
    if filename.startswith("scholarships/"):
        return send_from_directory(str(ASSETS_DIR / "scholarships"), filename[len("scholarships/"):])

    # Fallback: serve any .css from CSS_DIR and any .js from JS_DIR
    if filename.endswith(".css"):
        css_path = CSS_DIR / filename
        if css_path.exists():
            return send_from_directory(str(CSS_DIR), filename, mimetype="text/css")
    if filename.endswith(".js"):
        js_path = JS_DIR / filename
        if js_path.exists():
            return send_from_directory(str(JS_DIR), filename, mimetype="text/javascript")

    return jsonify({"error": "Not found"}), 404

@app.before_request
def ensure_db():
    global _DB_READY
    if request.endpoint in {"healthz", "static_files"}:
        return
    if not _DB_READY:
        init_db()
        _DB_READY = True


# Page routes

@app.route('/google8dc38f175c09ccbc.html')
def google_verify():
    return 'google-site-verification: google8dc38f175c09ccbc.html'

# Public, unauthenticated pages worth indexing — dashboards, admin, and
# transactional pages (forgot-password, accept-invite) are deliberately
# left out since they're either auth-gated or have no independent SEO value.
SITEMAP_PAGES = [
    ("/login", "1.0"),
    ("/register", "0.8"),
    ("/directory", "0.9"),
    ("/materials", "0.8"),
    ("/opportunities", "0.9"),
    ("/announcements", "0.6"),
    ("/organizations", "0.6"),
    ("/support", "0.4"),
    ("/privacy", "0.3"),
    ("/terms", "0.3"),
]

@app.route("/sitemap.xml")
def sitemap():
    base = "https://eduportalss.solomonleek.tech"
    urls = "".join(
        f"<url><loc>{base}{path}</loc><priority>{priority}</priority></url>"
        for path, priority in SITEMAP_PAGES
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    return Response(xml, mimetype="application/xml")

@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    return render_template("login.html", google_client_id=GOOGLE_CLIENT_ID)

@app.route("/register")
def register_page():
    return render_template("register.html", google_client_id=GOOGLE_CLIENT_ID)

@app.route("/terms")
def terms_page():
    return render_template("terms.html")

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")

@app.route("/support")
def support_page():
    return render_template("support.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/directory")
def directory_page():
    return render_template("directory.html")

@app.route("/materials")
def materials_page():
    return render_template("materials.html")

@app.route("/opportunities")
def opportunities_page():
    return render_template("opportunities.html")

@app.route("/announcements")
def announcements_page():
    return render_template("announcements.html")

@app.route("/my-applications")
def my_applications_page():
    return render_template("my-applications.html")

@app.route("/bookmarks")
def bookmarks_page():
    return render_template("bookmarks.html")

@app.route("/profile")
def profile_page():
    return render_template("profile.html")

@app.route("/settings")
def settings_page():
    return render_template("settings.html")

@app.route("/admin")
def admin_page():
    return render_template("admin.html")

@app.route("/school-dashboard")
def school_dashboard_page():
    return render_template("school-dashboard.html")

@app.route("/ngo-dashboard")
def ngo_dashboard_page():
    return render_template("ngo-dashboard.html")

@app.route("/org-dashboard")
def org_dashboard_page():
    return render_template("org-dashboard.html")

@app.route("/organizations")
def organizations_page():
    return render_template("organizations.html")

@app.route("/schools/<int:school_id>")
def school_profile(school_id: int):
    return render_template("school.html", school_id=school_id)

# Auth API

@app.route("/api/login", methods=["POST"])
@limiter.limit("10 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    password   = (data.get("password") or "").strip()
    if not identifier or not password:
        return api_err("identifier and password are required")
    # Normalise: lowercase for email lookup; keep original for phone lookup
    id_lower = identifier.lower()
    # Strip spaces from phone for a normalised comparison
    id_phone = identifier.replace(" ", "")
    user = query_one(
        "SELECT * FROM users WHERE lower(email)=? OR replace(phone,' ','')=?",
        (id_lower, id_phone),
    )
    if not user:
        return api_err("Invalid credentials", 401)
    verified = int(user.get("verified", 0))
    if verified == 0:
        return api_err("Please verify your email address before signing in. Check your inbox for the verification link.", 403)
    if verified < 0:
        return api_err("This account is deactivated", 403)
    if not int(user.get("has_password", 1)):
        return api_err(
            "This account signed up with Google. Use \"Continue with Google\" above, "
            "or tap \"Forgot password?\" to set one.", 401,
        )
    try:
        valid = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    except Exception:
        valid = False
    if not valid:
        return api_err("Invalid credentials", 401)
    return jsonify({
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"], "state": user["state"], "school_id": user["school_id"], "ngo_id": user["ngo_id"], "avatar": user["avatar"] or None},
    })

def _upsert_email_verification(user_id, token, expires_at):
    if is_mysql():
        sql = """INSERT INTO email_verifications (user_id, token, expires_at)
                 VALUES (?, ?, ?)
                 ON DUPLICATE KEY UPDATE
                 token=VALUES(token), expires_at=VALUES(expires_at), created_at=CURRENT_TIMESTAMP"""
    else:
        sql = """INSERT INTO email_verifications (user_id, token, expires_at)
                 VALUES (?, ?, ?)
                 ON CONFLICT (user_id) DO UPDATE SET
                 token=excluded.token, expires_at=excluded.expires_at, created_at=CURRENT_TIMESTAMP"""
    execute(sql, (user_id, token, expires_at))


def _create_password_reset_token(user_id: int) -> str:
    """Generate a fresh single-use reset token, store it (replacing any
    still-pending one for this user), and return the raw token to send."""
    token = secrets.token_urlsafe(32)
    if is_mysql():
        reset_sql = """INSERT INTO password_resets (user_id, token, created_at)
                       VALUES (?,?,CURRENT_TIMESTAMP)
                       ON DUPLICATE KEY UPDATE token=VALUES(token), created_at=CURRENT_TIMESTAMP"""
    else:
        reset_sql = """INSERT INTO password_resets (user_id, token, created_at)
                       VALUES (?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT (user_id) DO UPDATE SET token=excluded.token, created_at=CURRENT_TIMESTAMP"""
    execute(reset_sql, (user_id, token))
    return token


def _create_invitation(role: str, ref_id: int, email: str) -> str:
    """Create a single-use invitation for `role` (linked to `ref_id` — a
    school/NGO/organization id) addressed to `email`; store only its bcrypt
    hash, and return the accept-invite link containing the raw token."""
    token = secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()
    token_hint = token[:8]
    execute(
        "INSERT INTO invitations (token_hash,token_hint,role,ref_id,email,used) VALUES (?,?,?,?,?,0)",
        (token_hash, token_hint, role, ref_id, email),
    )
    base_url = request.host_url.rstrip("/")
    return f"{base_url}/accept-invite?token={token}"


def _onboard_and_invite(
    admin_id: int, action: str, target_type: str, target_id: int, role: str, email: str,
    invite_verb: str, account_label: str, invite_note: str, subject_label: str,
) -> dict:
    """Shared tail of every admin-onboarding route (create org / school / NGO):
    audit-log the creation, issue a single-use invite link, email it, and
    return the {id, invite_link, email_sent} fields every one of those
    routes' JSON responses shares — caller merges in its own "message"."""
    log_audit(admin_id, action, target_type, target_id)
    invite_link = _create_invitation(role, target_id, email)
    body = (
        f"Hello,\n\n"
        f"You have been invited to {invite_verb} on EduPortal South Sudan.\n\n"
        f"Click the link below to create your {account_label}:\n{invite_link}\n\n"
        f"{invite_note}\n\nEduPortal South Sudan"
    )
    email_sent = send_email(email, f"EduPortal — {subject_label}", body)
    return {"id": target_id, "invite_link": invite_link, "email_sent": email_sent}


@app.route("/api/register", methods=["POST"])
@limiter.limit("5 per minute")
def api_register():
    data   = request.get_json(silent=True) or {}
    name   = (data.get("name") or "").strip()[:120]
    email  = (data.get("email") or "").strip().lower()[:120] or None
    phone  = (data.get("phone") or "").strip()[:30] or None
    password = (data.get("password") or "").strip()
    role   = (data.get("role") or "student").strip().lower()
    state  = (data.get("state") or "").strip()[:80]
    county = (data.get("county") or "").strip()[:80]
    if not name or not password:
        return api_err("name and password are required")
    if len(password) < 8:
        return api_err("Password must be at least 8 characters")
    if role not in {"student","parent","teacher","school_admin","ngo_officer","org_publisher"}:
        return api_err("Invalid role")
    if query_one("SELECT id FROM users WHERE email=? OR phone=?", (email, phone)):
        return api_err("An account with those details already exists", 409)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # Accounts with an email start unverified; phone-only accounts are auto-verified
    needs_verification = bool(email)
    uid = execute(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,?,?)",
        (name, email, phone, pw_hash, role, state, county, 0 if needs_verification else 1),
    )
    user = query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not user:
        return api_err("Registration failed", 500)
    if needs_verification:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        _upsert_email_verification(uid, token, expires_at)
        base_url = request.host_url.rstrip("/")
        verify_url = f"{base_url}/api/verify-email?token={token}"
        email_sent = send_verification_email(email, name, verify_url)
        response: dict = {
            "message": "Registration successful. Please check your email to verify your account.",
            "email_verification_required": True,
        }
        if not email_sent:
            response["dev_verify_url"] = verify_url
            response["note"] = "Configure SMTP_HOST in .env to send verification emails in production."
        return jsonify(response), 201
    return jsonify({
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"], "school_id": user["school_id"], "ngo_id": user["ngo_id"], "avatar": user["avatar"] or None},
    }), 201

@app.route("/api/verify-email")
def api_verify_email():
    token = (request.args.get("token") or "").strip()
    if not token:
        return api_err("Verification token is required")
    row = query_one(
        "SELECT * FROM email_verifications WHERE token=?",
        (token,),
    )
    if not row:
        return api_err("Invalid or already-used verification link", 400)
    # Check expiry
    expires_at = parse_utc_iso(row.get("expires_at"))
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        return api_err("This verification link has expired. Please request a new one.", 400)
    execute("UPDATE users SET verified=1 WHERE id=?", (row["user_id"],))
    execute("DELETE FROM email_verifications WHERE user_id=?", (row["user_id"],))
    user = query_one("SELECT * FROM users WHERE id=?", (row["user_id"],))
    if not user:
        return api_err("Account not found", 404)
    return jsonify({
        "message": "Email verified successfully. You can now sign in.",
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
    })

@app.route("/api/auth/google", methods=["POST"])
@limiter.limit("15 per minute")
def api_auth_google():
    data = request.get_json(silent=True) or {}
    credential = (data.get("credential") or "").strip()
    if not credential:
        return api_err("credential is required")
    claims = verify_google_token(credential)
    if not claims:
        return api_err("Invalid or unverified Google credential", 401)
    email = (claims.get("email") or "").strip().lower()
    if not email:
        return api_err("Google account has no email", 400)

    user = query_one("SELECT * FROM users WHERE lower(email)=?", (email,))
    if user:
        if int(user.get("verified", 0)) < 0:
            return api_err("This account is deactivated", 403)
        if int(user.get("verified", 0)) == 0:
            # Google already proved ownership of this email — no need to also click a verify link
            execute("UPDATE users SET verified=1 WHERE id=?", (user["id"],))
            user = query_one("SELECT * FROM users WHERE id=?", (user["id"],))
    else:
        # Brand-new Google sign-in: self-service accounts never get "admin" —
        # that's assigned by an existing admin, not chosen at signup — so a
        # role must be one of the ordinary account types. The frontend calls
        # this same endpoint twice for a first-time signup: once with just
        # the credential (gets this "pick a role" response back) and again
        # with the credential plus the chosen role once the person answers.
        name = (claims.get("name") or email.split("@")[0]).strip()[:120]
        role = (data.get("role") or "").strip().lower()
        if role not in {"student", "parent", "teacher", "school_admin", "ngo_officer"}:
            return jsonify({"needs_role": True, "name": name, "email": email})
        avatar = (claims.get("picture") or "").strip() or None
        placeholder_hash = bcrypt.hashpw(secrets.token_urlsafe(32).encode(), bcrypt.gensalt()).decode()
        uid = execute(
            "INSERT INTO users (name,email,password_hash,role,verified,avatar,has_password) VALUES (?,?,?,?,1,?,0)",
            (name, email, placeholder_hash, role, avatar),
        )
        user = query_one("SELECT * FROM users WHERE id=?", (uid,))

    return jsonify({
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"], "school_id": user["school_id"], "ngo_id": user["ngo_id"], "avatar": user["avatar"] or None},
    })


@app.route("/api/resend-verification", methods=["POST"])
@limiter.limit("3 per minute")
def api_resend_verification():
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return api_err("email is required")
    user = query_one("SELECT * FROM users WHERE lower(email)=?", (email,))
    # Always return success to avoid enumeration
    if user and int(user.get("verified", 1)) == 0:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        _upsert_email_verification(user["id"], token, expires_at)
        base_url = request.host_url.rstrip("/")
        verify_url = f"{base_url}/api/verify-email?token={token}"
        send_verification_email(email, user["name"], verify_url)
    return jsonify({"message": "If that email is registered and unverified, a new link has been sent."})

@app.route("/api/refresh", methods=["POST"])
@limiter.limit("30 per minute")
def api_refresh():
    data = request.get_json(silent=True) or {}
    raw_token = (data.get("refresh_token") or "").strip()
    if not raw_token:
        return api_err("refresh_token is required")
    user = verify_refresh_token(raw_token)
    if not user:
        return api_err("Invalid or expired refresh token", 401)
    return jsonify({
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
    })

@app.route("/api/logout", methods=["POST"])
def api_logout():
    data = request.get_json(silent=True) or {}
    raw_token = (data.get("refresh_token") or "").strip()
    if raw_token:
        revoke_refresh_token(raw_token)
    return jsonify({"message": "Logged out"})


@app.route("/api/me")
@require_auth
def api_me():
    u = request.current_user  # type: ignore[attr-defined]
    return jsonify({"user": {
        "id": u["id"], "name": u["name"], "email": u["email"], "phone": u["phone"],
        "role": u["role"], "state": u["state"], "county": u["county"],
        "notify_email": bool(u["notify_email"]), "notify_sms": bool(u["notify_sms"]),
        "notify_inapp": bool(u["notify_inapp"]),
        "avatar": u["avatar"] or None,
        "grade": u["grade"] or "", "school_name": u["school_name"] or "",
        "child_school": u["child_school"] or "", "child_grade": u["child_grade"] or "",
        "subjects": u["subjects"] or "", "institution": u["institution"] or "",
        "experience_years": u["experience_years"], "managed_school": u["managed_school"] or "",
        "position": u["position"] or "",
        "school_id": u["school_id"],
        "ngo_id": u["ngo_id"],
    }})

@app.route("/api/me/avatar", methods=["POST"])
@require_auth
def api_me_avatar():
    u = request.current_user  # type: ignore[attr-defined]
    if "avatar" not in request.files:
        return api_err("No file uploaded")
    try:
        ext, data = _read_uploaded_image(request.files["avatar"], MAX_AVATAR_BYTES)
    except ValueError as exc:
        return api_err(str(exc), 400)
    filename = f"user_{u['id']}.{ext}"
    stored = save_file(UPLOAD_FOLDER, filename, io.BytesIO(data))
    avatar_url = _public_file_url(stored, "avatars", filename)
    execute("UPDATE users SET avatar=? WHERE id=?", (avatar_url, u["id"]))
    return jsonify({"avatar": avatar_url})

def _school_owner_error(u: dict, school_id: int):
    """None if `u` may edit `school_id` (admin, or that school's own
    school_admin); otherwise a 403 api_err() response for the caller to
    return directly."""
    if u["role"] == "admin" or (u["role"] == "school_admin" and u["school_id"] == school_id):
        return None
    return api_err("You are not authorised to edit this school", 403)

@app.route("/api/schools/<int:school_id>/logo", methods=["POST"])
@require_auth
def api_school_logo(school_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    err = _school_owner_error(u, school_id)
    if err:
        return err
    if "logo" not in request.files:
        return api_err("No file uploaded")
    try:
        ext, data = _read_uploaded_image(request.files["logo"], MAX_AVATAR_BYTES)
    except ValueError as exc:
        return api_err(str(exc), 400)
    filename = f"school_{school_id}.{ext}"
    stored = save_file(LOGOS_FOLDER, filename, io.BytesIO(data))
    logo_url = _public_file_url(stored, "logos", filename)
    execute("UPDATE schools SET logo_url=? WHERE id=?", (logo_url, school_id))
    return jsonify({"logo_url": logo_url})

@app.route("/api/my-ngo/logo", methods=["POST"])
@require_role("ngo_officer")
def api_ngo_logo():
    u = request.current_user  # type: ignore[attr-defined]
    my_ngo_id = _current_ngo_id(u)
    if not my_ngo_id:
        return api_err("Save your organisation profile before uploading a logo", 400)
    if "logo" not in request.files:
        return api_err("No file uploaded")
    try:
        ext, data = _read_uploaded_image(request.files["logo"], MAX_AVATAR_BYTES)
    except ValueError as exc:
        return api_err(str(exc), 400)
    filename = f"ngo_{my_ngo_id}.{ext}"
    stored = save_file(LOGOS_FOLDER, filename, io.BytesIO(data))
    logo_url = _public_file_url(stored, "logos", filename)
    execute("UPDATE ngos SET logo_url=? WHERE id=?", (logo_url, my_ngo_id))
    return jsonify({"logo_url": logo_url})

@app.route("/api/me", methods=["PUT"])
@require_auth
def api_me_update():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    allowed = ["name","email","phone","state","county",
               "notify_email","notify_sms","notify_inapp",
               "grade","school_name","child_school","child_grade",
               "subjects","institution","experience_years","managed_school","position"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No updatable fields provided")
    params.append(u["id"])
    execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Profile updated"})

@app.route("/api/change-password", methods=["POST"])
@require_auth
def api_change_password():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    current  = (data.get("current_password") or "").strip()
    new_pass = (data.get("new_password") or "").strip()
    if not current or not new_pass:
        return api_err("current_password and new_password are required")
    if len(new_pass) < 8:
        return api_err("New password must be at least 8 characters")
    try:
        valid = bcrypt.checkpw(current.encode(), u["password_hash"].encode())
    except Exception:
        valid = False
    if not valid:
        return api_err("Current password is incorrect", 401)
    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, u["id"]))
    # Password changed — sign out every other session, then re-issue for this one
    revoke_all_refresh_tokens(u["id"])
    return jsonify({
        "message": "Password changed",
        "token": make_token(u),
        "refresh_token": make_refresh_token(u["id"]),
    })

@app.route("/api/deactivate-account", methods=["POST"])
@require_auth
def api_deactivate_account():
    u = request.current_user  # type: ignore[attr-defined]
    execute("UPDATE users SET verified=-1 WHERE id=?", (u["id"],))
    revoke_all_refresh_tokens(u["id"])
    return jsonify({"message": "Account deactivated"})


# Stats

@app.route("/api/stats")
def api_stats():
    return jsonify({
        "schools":       count("SELECT COUNT(*) AS count FROM schools"),
        "materials":     count("SELECT COUNT(*) AS count FROM materials WHERE approved=1"),
        "scholarships":  count("SELECT COUNT(*) AS count FROM scholarships WHERE approved=1"),
        "announcements": count("SELECT COUNT(*) AS count FROM announcements WHERE approved=1"),
        "users":         count("SELECT COUNT(*) AS count FROM users"),
        "states": 10,
    })

# Schools

@app.route("/api/schools")
def api_schools():
    state   = request.args.get("state","").strip()
    level   = request.args.get("level","").strip()
    type_   = request.args.get("type","").strip()
    boarding = request.args.get("boarding","").strip()
    ownership = request.args.get("ownership","").strip()
    search  = request.args.get("search","").strip()
    page    = max(1, int(request.args.get("page","1") or 1))
    per_page = min(max(1, int(request.args.get("per_page","6") or 6)), 200)
    sql = ("SELECT id,name,state,county,level,type,status,enrollment,boarding,ownership,description,"
           "registration_number,registration_verified,logo_url FROM schools WHERE approved=1")
    params: list = []
    sql = _append_equals_filters(sql, params, [
        (state, "state"), (level, "level"), (type_, "type"),
        (boarding, "boarding"), (ownership, "ownership"),
    ])
    if search:
        sql += " AND (name LIKE ? OR county LIKE ? OR state LIKE ?)"
        t = f"%{search}%"; params.extend([t,t,t])
    total = count(f"SELECT COUNT(*) AS count FROM ({sql}) AS t", tuple(params))  # noqa: S608
    sql += f" ORDER BY name LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return jsonify({"items": query_all(sql, tuple(params)), "total": total, "page": page, "per_page": per_page})

@app.route("/api/schools/<int:school_id>")
def api_school_detail(school_id: int):
    school = query_one("SELECT * FROM schools WHERE id=?", (school_id,))
    if not school:
        return api_err("School not found", 404)
    if not school["approved"]:
        u = get_current_user()
        is_owner = u and (u["role"] == "admin" or (u["role"] == "school_admin" and u["school_id"] == school_id))
        if not is_owner:
            return api_err("School not found", 404)
    return jsonify({"school": school})

@app.route("/api/schools/<int:school_id>", methods=["PUT"])
@require_auth
def api_school_update(school_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    err = _school_owner_error(u, school_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    allowed = ["name","state","county","level","type","curriculum","contact_name",
               "phone","email","capacity","status","enrollment","language","boarding",
               "ownership","hours","description",
               "registration_number","year_established","logo_url","address",
               "mission","vision","core_values","subjects_offered",
               "age_requirements","entry_grades","fees_structure","how_to_apply",
               "requirements_text",
               "headteacher_name","teaching_staff_count","classroom_count",
               "has_library","has_laboratory","has_sports_facilities",
               "has_water_sanitation","has_electricity","has_sports_clubs",
               "has_arts_culture","has_academic_clubs","has_student_government",
               "extracurricular_other"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No updatable fields provided")
    params.append(school_id)
    execute(f"UPDATE schools SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "School updated"})

@app.route("/api/schools/<int:school_id>/requirements", methods=["PUT"])
@require_auth
def api_school_requirements_update(school_id: int):
    """Replace all admission requirements for a school."""
    u = request.current_user  # type: ignore[attr-defined]
    err = _school_owner_error(u, school_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    execute("DELETE FROM admission_requirements WHERE school_id=?", (school_id,))
    for item in items:
        label = (item.get("item_label") or "").strip()
        if not label:
            continue
        execute(
            "INSERT INTO admission_requirements (school_id,item_label,is_required,notes) VALUES (?,?,?,?)",
            (school_id, label, 1 if item.get("is_required") else 0, (item.get("notes") or "").strip() or None),
        )
    return jsonify({"message": "Requirements updated"})

@app.route("/api/schools/<int:school_id>/requirements")
def api_school_requirements(school_id: int):
    items = query_all("SELECT id,item_label,is_required,notes FROM admission_requirements WHERE school_id=? ORDER BY id", (school_id,))
    return jsonify({"items": items})

@app.route("/api/schools/<int:school_id>/requirements-doc", methods=["POST"])
@require_auth
def api_school_requirements_doc(school_id: int):
    """A single admission-requirements document (PDF or scanned image) a
    school can attach alongside the itemised text checklist above — not a
    replacement for it, since some schools only have one or the other."""
    u = request.current_user  # type: ignore[attr-defined]
    err = _school_owner_error(u, school_id)
    if err:
        return err
    if "doc" not in request.files:
        return api_err("No file uploaded")
    f = request.files["doc"]
    if not f.filename:
        return api_err("Empty filename")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ({"pdf"} | ALLOWED_EXTENSIONS):
        return api_err("Only PDF, JPG, PNG, GIF, or WEBP files are allowed")
    if ext == "pdf":
        if not _is_valid_pdf(f.stream):
            return api_err("File content does not match a valid PDF", 400)
    elif not _is_valid_image(f.stream):
        return api_err("File content does not match a recognised image format", 400)
    data = f.stream.read()
    if len(data) > MAX_MATERIAL_BYTES:
        return api_err(f"File must be under {MAX_MATERIAL_BYTES // (1024 * 1024)} MB", 400)
    filename = f"school_{school_id}_requirements.{ext}"
    stored = save_file(REQUIREMENTS_FOLDER, filename, io.BytesIO(data))
    doc_url = _public_file_url(stored, "requirements", filename)
    execute("UPDATE schools SET requirements_doc_url=? WHERE id=?", (doc_url, school_id))
    return jsonify({"requirements_doc_url": doc_url})

@app.route("/api/schools/<int:school_id>/exam-results", methods=["PUT"])
@require_auth
def api_school_exam_results_update(school_id: int):
    """Replace all national exam pass-rate entries for a school."""
    u = request.current_user  # type: ignore[attr-defined]
    err = _school_owner_error(u, school_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    execute("DELETE FROM school_exam_results WHERE school_id=?", (school_id,))
    for item in items:
        subject = (item.get("subject") or "").strip()[:80]
        year = item.get("year")
        pass_rate = item.get("pass_rate")
        if not subject or not year or pass_rate is None:
            continue
        execute(
            "INSERT INTO school_exam_results (school_id,year,subject,pass_rate) VALUES (?,?,?,?)",
            (school_id, int(year), subject, float(pass_rate)),
        )
    return jsonify({"message": "Exam results updated"})

@app.route("/api/schools/<int:school_id>/exam-results")
def api_school_exam_results(school_id: int):
    items = query_all(
        "SELECT id,year,subject,pass_rate FROM school_exam_results WHERE school_id=? ORDER BY year DESC,subject",
        (school_id,),
    )
    return jsonify({"items": items})

# Materials

@app.route("/api/materials")
def api_materials():
    subject  = request.args.get("subject","").strip()
    grade    = request.args.get("grade","").strip()
    year     = request.args.get("year","").strip()
    doc_type = request.args.get("type","").strip()
    search   = request.args.get("search","").strip()
    sort     = request.args.get("sort","").strip()
    approved = request.args.get("approved","1").strip()
    page     = max(1, int(request.args.get("page","1") or 1))
    per_page = 12
    approved_val = 0 if approved == "0" else 1
    sql = "SELECT id,title,subject,grade,`year`,type,file_size,preview_text,file_path,thumbnail_path,created_at,rejection_reason,uploaded_by FROM materials WHERE approved=?"
    params: list = [approved_val]
    # Subject is a free-text field now (teachers can type any subject, not
    # just the 4 suggested ones), so match it as a substring rather than
    # requiring an exact, exact-case match against what's stored.
    if subject:  sql += " AND subject LIKE ?"; params.append(f"%{subject}%")
    sql = _append_equals_filters(sql, params, [(grade, "grade"), (doc_type, "type")])
    if year:     sql += " AND `year`=?";   params.append(int(year))
    if search:
        sql += " AND (title LIKE ? OR subject LIKE ?)"
        t = f"%{search}%"; params.extend([t,t])
    total = count(f"SELECT COUNT(*) AS count FROM ({sql}) AS t", tuple(params))  # noqa: S608
    order_clause = {
        "oldest": "ORDER BY `year` ASC, title ASC",
        "title":  "ORDER BY title ASC",
    }.get(sort, "ORDER BY `year` DESC, title ASC")
    sql += f" {order_clause} LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return jsonify({"items": query_all(sql, tuple(params)), "total": total, "page": page, "per_page": per_page})

@app.route("/api/materials/<int:material_id>")
def api_material_detail(material_id: int):
    row = query_one("SELECT id,title,subject,grade,`year`,type,file_size,preview_text,file_path,thumbnail_path,created_at FROM materials WHERE id=? AND approved=1", (material_id,))
    if not row:
        return api_err("Material not found", 404)
    return jsonify({"material": row})

@app.route("/api/materials", methods=["POST"])
@require_role("teacher","school_admin")
def api_materials_submit():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    title    = (data.get("title") or "").strip()
    subject  = (data.get("subject") or "").strip()
    grade    = (data.get("grade") or "").strip()
    year     = data.get("year")
    doc_type = (data.get("type") or "").strip()
    if not all([title, subject, grade, year, doc_type]):
        return api_err("title, subject, grade, year, and type are required")
    year_value = int(str(year))
    normalized_type = doc_type.lower()
    if normalized_type in {"tutorial", "video", "video tutorial"}:
        normalized_type = "tutorial video"
    mid = execute(
        "INSERT INTO materials (title,subject,grade,`year`,type,uploaded_by,approved) VALUES (?,?,?,?,?,?,0)",
        (title, subject, grade, year_value, normalized_type, u["email"] or u["phone"]),
    )
    return jsonify({"message": "Material submitted for review", "id": mid}), 201


def _is_material_owner(material: dict, u: dict) -> bool:
    owner = material.get("uploaded_by") or ""
    return owner != "" and owner in {u.get("email") or "", u.get("phone") or ""}


@app.route("/api/materials/<int:material_id>", methods=["PUT"])
@require_role("teacher", "school_admin", "admin")
def api_material_update(material_id: int):
    u   = request.current_user  # type: ignore[attr-defined]
    mat = query_one("SELECT id,uploaded_by FROM materials WHERE id=?", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    if u["role"] != "admin" and not _is_material_owner(mat, u):
        return api_err("You can only edit your own materials", 403)
    data    = request.get_json(silent=True) or {}
    allowed = ["title", "subject", "grade", "type"]
    sets, params = _build_update_clause(data, allowed)
    if "year" in data and data["year"]:
        sets.append("`year`=?")
        params.append(int(data["year"]))
    if not sets:
        return api_err("No fields to update")
    if u["role"] != "admin":
        sets.append("approved=0")  # edits go back through moderation
    params.append(material_id)
    execute(f"UPDATE materials SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Material updated"})


@app.route("/api/materials/<int:material_id>", methods=["DELETE"])
@require_role("teacher", "school_admin", "admin")
def api_material_delete(material_id: int):
    u   = request.current_user  # type: ignore[attr-defined]
    mat = query_one("SELECT id,uploaded_by FROM materials WHERE id=?", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    if u["role"] != "admin" and not _is_material_owner(mat, u):
        return api_err("You can only delete your own materials", 403)
    execute("DELETE FROM bookmarks WHERE item_type='material' AND item_id=?", (material_id,))
    execute("DELETE FROM materials WHERE id=?", (material_id,))
    return jsonify({"message": "Material deleted"})


@app.route("/api/materials/<int:material_id>/upload", methods=["POST"])
@require_role("teacher", "school_admin")
def api_material_upload_file(material_id: int):
    """Attach a PDF file to an existing material record."""
    u = request.current_user  # type: ignore[attr-defined]
    mat = query_one("SELECT * FROM materials WHERE id=?", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    # Only the uploader or admin can attach a file
    if u["role"] != "admin" and mat.get("uploaded_by") not in (u.get("email"), u.get("phone")):
        return api_err("Forbidden", 403)
    if "file" not in request.files:
        return api_err("No file provided")
    f = request.files["file"]
    if not f.filename:
        return api_err("Empty filename")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_MATERIAL_EXTS:
        return api_err("Only PDF, MP4, WebM, OGG, or M4V files are allowed")
    if ext in VIDEO_EXTENSIONS and not _is_valid_video(f.stream):
        return api_err("File content does not match a recognised video format", 400)
    if ext == "pdf" and not _is_valid_pdf(f.stream):
        return api_err("File content does not match a valid PDF", 400)
    safe_name = f"material_{material_id}_{secure_filename(f.filename)}"
    # Read into memory once so we can get size and still pass stream to storage
    data = f.stream.read()
    file_size = f"{len(data) // 1024} KB"
    stored = save_file(MATERIALS_FOLDER, safe_name, io.BytesIO(data))
    file_path = _public_file_url(stored, "materials", safe_name)

    # Best-effort real preview (first PDF page / a video frame) in place of
    # the generic document/play-button icon — see the two generators above.
    thumbnail_path = None
    thumb_bytes = _generate_pdf_thumbnail(data) if ext == "pdf" else _generate_video_thumbnail(data, ext)
    if thumb_bytes:
        thumb_name = f"material_{material_id}_thumb.jpg"
        thumb_stored = save_file(MATERIALS_FOLDER, thumb_name, io.BytesIO(thumb_bytes))
        thumbnail_path = _public_file_url(thumb_stored, "materials", thumb_name)

    execute("UPDATE materials SET file_path=?, file_size=?, thumbnail_path=? WHERE id=?",
            (file_path, file_size, thumbnail_path, material_id))
    return jsonify({"message": "File uploaded", "file_path": file_path, "thumbnail_path": thumbnail_path})


@app.route("/api/materials/<int:material_id>/stream")
def api_material_stream(material_id: int):
    """Serve a material file inline (view in browser / watch video).
    Opened via plain <a target="_blank"> navigation, which can't set an
    Authorization header, so also accept the token as ?token= — same
    workaround as /api/notifications/stream."""
    user = get_current_user()
    if not user:
        token = (request.args.get("token") or "").strip()
        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                user = query_one("SELECT * FROM users WHERE id=?", (payload["sub"],))
            except jwt.PyJWTError:
                user = None
    if not user:
        return api_err("Authentication required", 401)
    mat = query_one("SELECT * FROM materials WHERE id=? AND approved=1", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    file_path_rel = mat.get("file_path")
    if not file_path_rel:
        return api_err("No file has been uploaded for this material yet", 404)
    # S3/Supabase-backed uploads store a full external URL — serve those by
    # redirecting instead of treating it as a local disk path, or every
    # material uploaded to S3 would 404 here despite uploading successfully.
    if file_path_rel.startswith("http://") or file_path_rel.startswith("https://"):
        return redirect(file_path_rel)
    clean_rel = file_path_rel.replace("/static/", "", 1).lstrip("/")
    disk_path = ASSETS_DIR / clean_rel
    if not disk_path.exists():
        return api_err("File not found on server", 404)
    return flask_send_file(
        str(disk_path),
        as_attachment=False,
        download_name=disk_path.name,
        mimetype=_material_mimetype(disk_path.name),
    )


@app.route("/api/materials/<int:material_id>/download")
@require_auth
def api_material_download(material_id: int):
    """Serve a material PDF for authenticated users."""
    u = request.current_user  # type: ignore[attr-defined]
    if u["role"] == "parent":
        return api_err("Parent accounts can view materials but not download them", 403)
    mat = query_one("SELECT * FROM materials WHERE id=? AND approved=1", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    file_path_rel = mat.get("file_path")
    if not file_path_rel:
        return api_err("No file has been uploaded for this material yet", 404)
    # S3/Supabase-backed uploads store a full external URL — serve those by
    # redirecting instead of treating it as a local disk path, or every
    # material uploaded to S3 would 404 here despite uploading successfully.
    if file_path_rel.startswith("http://") or file_path_rel.startswith("https://"):
        execute("UPDATE materials SET download_count=download_count+1 WHERE id=?", (material_id,))
        return redirect(file_path_rel)
    clean_rel = file_path_rel.replace("/static/", "", 1).lstrip("/")
    disk_path = ASSETS_DIR / clean_rel
    if not disk_path.exists():
        return api_err("File not found on server", 404)
    execute("UPDATE materials SET download_count=download_count+1 WHERE id=?", (material_id,))
    return flask_send_file(
        str(disk_path),
        as_attachment=True,
        download_name=disk_path.name,
        mimetype=_material_mimetype(disk_path.name),
    )

# Organizations

VALID_ORG_TYPES = {
    "Ministry of General Education",
    "State Ministry of Education",
    "University",
    "College",
    "School",
    "Examination Body",
    "NGO",
    "Scholarship Provider",
}

@app.route("/api/organizations")
def api_organizations():
    org_type = request.args.get("org_type", "").strip()
    state    = request.args.get("state", "").strip()
    verified = request.args.get("verified", "1").strip()
    sql = "SELECT id,name,org_type,state,email,phone,website,description,verified FROM organizations WHERE verified=?"
    params: list = [0 if verified == "0" else 1]
    if org_type: sql += " AND org_type=?"; params.append(org_type)
    if state:    sql += " AND state=?";    params.append(state)
    sql += " ORDER BY org_type, name"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/organizations/<int:org_id>")
def api_organization_detail(org_id: int):
    org = query_one("SELECT * FROM organizations WHERE id=?", (org_id,))
    if not org:
        return api_err("Organisation not found", 404)
    announcements = query_all(
        "SELECT id,title,body,audience,priority,expires_at,created_at FROM announcements "
        "WHERE org_id=? AND org_type=? AND approved=1 ORDER BY created_at DESC LIMIT 10",
        (org_id, org["org_type"]),
    )
    return jsonify({"organization": org, "announcements": announcements})

@app.route("/api/admin/organizations", methods=["POST"])
@require_role("admin")
def api_admin_create_org():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    name     = (data.get("name") or "").strip()[:200]
    org_type = (data.get("org_type") or "").strip()
    state    = (data.get("state") or "").strip()[:80] or None
    email    = (data.get("email") or "").strip()[:120] or None
    phone    = (data.get("phone") or "").strip()[:30] or None
    website  = (data.get("website") or "").strip()[:200] or None
    description = (data.get("description") or "").strip() or None
    if not name or org_type not in VALID_ORG_TYPES:
        return api_err(f"name and a valid org_type are required. Valid types: {', '.join(sorted(VALID_ORG_TYPES))}")
    if not email:
        return api_err("A contact email is required to send the admin invitation")
    oid = execute(
        "INSERT INTO organizations (name,org_type,state,email,phone,website,description,verified) VALUES (?,?,?,?,?,?,?,1)",
        (name, org_type, state, email, phone, website, description),
    )
    result = _onboard_and_invite(
        u["id"], "create_org", "organization", oid, "org_publisher", email,
        invite_verb=f"publish announcements on behalf of {name}",
        account_label="account",
        invite_note="This link is single-use.",
        subject_label=f"Publisher Invitation for {name}",
    )
    return jsonify({"message": "Organisation created and invitation sent", **result}), 201

@app.route("/api/admin/organizations/<int:org_id>", methods=["PUT"])
@require_role("admin")
def api_admin_update_org(org_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    allowed = ["name", "org_type", "state", "email", "phone", "website", "description", "verified"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No updatable fields provided")
    params.append(org_id)
    execute(f"UPDATE organizations SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    log_audit(u["id"], "update_org", "organization", org_id)
    return jsonify({"message": "Organisation updated"})

@app.route("/api/admin/organizations/<int:org_id>", methods=["DELETE"])
@require_role("admin")
def api_admin_delete_org(org_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    execute("DELETE FROM organizations WHERE id=?", (org_id,))
    log_audit(u["id"], "delete_org", "organization", org_id)
    return jsonify({"message": "Organisation deleted"})

@app.route("/api/organizations/request", methods=["POST"])
def api_org_join_request():
    """Public endpoint — any visitor can request their org be listed.
    Creates an unverified record; admin reviews and sends an invite."""
    data        = request.get_json(silent=True) or {}
    name        = (data.get("name") or "").strip()[:200]
    org_type    = (data.get("org_type") or "").strip()
    state       = (data.get("state") or "").strip()[:80] or None
    email       = (data.get("email") or "").strip()[:120] or None
    phone       = (data.get("phone") or "").strip()[:30] or None
    website     = (data.get("website") or "").strip()[:200] or None
    description = (data.get("description") or "").strip() or None
    if not name or org_type not in VALID_ORG_TYPES:
        return api_err(f"name and a valid org_type are required. Valid types: {', '.join(sorted(VALID_ORG_TYPES))}")
    if not email:
        return api_err("A contact email is required")
    existing = query_one(
        "SELECT id FROM organizations WHERE lower(email)=? AND verified=0",
        (email.lower(),),
    )
    if existing:
        return jsonify({"message": "A request from this email is already pending review."}), 200
    oid = execute(
        "INSERT INTO organizations (name,org_type,state,email,phone,website,description,verified) "
        "VALUES (?,?,?,?,?,?,?,0)",
        (name, org_type, state, email, phone, website, description),
    )
    return jsonify({
        "message": "Request submitted. Our team will review and contact you at the email provided.",
        "id": oid,
    }), 201

@app.route("/api/my-org/profile", methods=["PUT"])
@require_role("org_publisher")
def api_my_org_profile_update():
    """Org publisher can update their own organisation's public profile."""
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    inv  = query_one(
        "SELECT ref_id FROM invitations WHERE email=? AND role='org_publisher' AND used=1 ORDER BY id DESC LIMIT 1",
        (u.get("email") or "",),
    )
    if not inv or not inv["ref_id"]:
        return api_err("No organisation linked to your account", 404)
    org_id = inv["ref_id"]
    allowed = ["name", "state", "email", "phone", "website", "description"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No updatable fields provided")
    params.append(org_id)
    execute(f"UPDATE organizations SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Organisation profile updated"})

# Announcements

@app.route("/api/announcements")
def api_announcements():
    source     = request.args.get("source", "").strip()      # legacy: source_type
    org_type   = request.args.get("org_type", "").strip()
    audience   = request.args.get("audience", "").strip()
    priority   = request.args.get("priority", "").strip()
    state      = request.args.get("state", "").strip()
    date_from  = request.args.get("date_from", "").strip()
    date_to    = request.args.get("date_to", "").strip()
    search     = request.args.get("search", "").strip()
    approved   = request.args.get("approved", "1").strip()
    approved_val = 0 if approved == "0" else 1
    today = datetime.now(timezone.utc).date().isoformat()
    sql = (
        "SELECT id,title,body,source_type,org_type,org_name,org_id,"
        "audience,priority,state,attachment_url,attachment_path,expires_at,created_at,"
        "rejection_reason,view_count "
        "FROM announcements WHERE approved=? AND (expires_at IS NULL OR expires_at='' OR date(expires_at) >= date(?))"
    )
    params: list = [approved_val, today]
    sql = _append_equals_filters(sql, params, [
        (source, "source_type"), (org_type, "org_type"),
        (audience, "audience"), (priority, "priority"),
    ])
    if state:     sql += " AND (state=? OR state IS NULL)";  params.append(state)
    if date_from: sql += " AND date(created_at) >= date(?)"; params.append(date_from)
    if date_to:   sql += " AND date(created_at) <= date(?)"; params.append(date_to)
    if search:
        sql += " AND (title LIKE ? OR body LIKE ? OR org_name LIKE ?)"
        t = f"%{search}%"; params.extend([t, t, t])
    sql += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, created_at DESC"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/announcements/<int:ann_id>/view", methods=["POST"])
def api_announcement_view(ann_id: int):
    """Announcements render inline as list cards with no separate detail page,
    so the frontend fires this once per card shown — a simple impression
    count admins can use to see which announcements get seen most."""
    execute("UPDATE announcements SET view_count=view_count+1 WHERE id=? AND approved=1", (ann_id,))
    return jsonify({"message": "ok"})

@app.route("/api/announcements", methods=["POST"])
@require_role("school_admin", "ngo_officer", "org_publisher", "admin")
def api_announcements_post():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    title          = (data.get("title") or "").strip()
    body           = (data.get("body") or "").strip()
    audience       = (data.get("audience") or "").strip()
    expires_at     = (data.get("expires_at") or "").strip() or None
    priority       = (data.get("priority") or "normal").strip()
    attachment_url = (data.get("attachment_url") or "").strip() or None
    ann_state      = (data.get("state") or "").strip() or None
    if not all([title, body, audience]):
        return api_err("title, body, and audience are required")
    if priority not in {"normal", "high", "urgent"}:
        priority = "normal"
    # Resolve org context from the posting user
    org_type = org_name = None
    org_id   = None
    if u["role"] == "org_publisher":
        # Find the org this user was invited to manage
        inv = query_one(
            "SELECT ref_id FROM invitations WHERE email=? AND role='org_publisher' AND used=1 ORDER BY id DESC LIMIT 1",
            (u.get("email") or "",),
        )
        if inv and inv["ref_id"]:
            org = query_one("SELECT id,name,org_type FROM organizations WHERE id=?", (inv["ref_id"],))
            if org:
                org_id   = org["id"]
                org_name = org["name"]
                org_type = org["org_type"]
    elif u["role"] == "school_admin":
        org_type = "School"
        if u.get("school_id"):
            school = query_one("SELECT name FROM schools WHERE id=?", (u["school_id"],))
            org_name = school["name"] if school else None
            org_id   = u["school_id"]
    elif u["role"] == "ngo_officer":
        org_type = "NGO"
        my_ngo_id = _current_ngo_id(u)
        ngo = query_one("SELECT id,org_name FROM ngos WHERE id=?", (my_ngo_id,)) if my_ngo_id else None
        if ngo:
            org_name = ngo["org_name"]
            org_id   = ngo["id"]
    elif u["role"] == "admin":
        org_type = (data.get("org_type") or "Ministry of General Education").strip()
        org_name = (data.get("org_name") or "").strip() or None
        org_id   = data.get("org_id")
    # Legacy source_type for backward compat
    source_type = org_type or (data.get("source_type") or "School").strip()
    approved = 1 if u["role"] == "admin" else 0
    aid = execute(
        "INSERT INTO announcements "
        "(title,body,source_type,source_id,org_type,org_name,org_id,"
        "audience,priority,state,attachment_url,expires_at,approved) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, body, source_type, u["id"], org_type, org_name, org_id,
         audience, priority, ann_state, attachment_url, expires_at, approved),
    )
    return jsonify({"message": "Announcement submitted for review", "id": aid}), 201

@app.route("/api/announcements/<int:ann_id>/upload", methods=["POST"])
@require_role("school_admin", "ngo_officer", "org_publisher", "admin")
def api_announcement_upload(ann_id: int):
    """Attach a PDF file to an existing announcement."""
    u = request.current_user  # type: ignore[attr-defined]
    ann = query_one("SELECT * FROM announcements WHERE id=?", (ann_id,))
    if not ann:
        return api_err("Announcement not found", 404)
    if u["role"] != "admin" and ann["source_id"] != u["id"]:
        return api_err("Forbidden", 403)
    if "file" not in request.files:
        return api_err("No file provided")
    f = request.files["file"]
    if not f.filename:
        return api_err("Empty filename")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in {"pdf"}:
        return api_err("Only PDF files are allowed for announcement attachments")
    if not _is_valid_pdf(f.stream):
        return api_err("File content does not match a valid PDF", 400)
    safe_name = f"ann_{ann_id}_{secure_filename(f.filename)}"
    ANNOUNCEMENTS_FOLDER.mkdir(parents=True, exist_ok=True)
    stored = save_file(ANNOUNCEMENTS_FOLDER, safe_name, f.stream)
    file_path = _public_file_url(stored, "announcements", safe_name)
    execute("UPDATE announcements SET attachment_path=? WHERE id=?", (file_path, ann_id))
    return jsonify({"message": "File uploaded", "attachment_path": file_path})


@app.route("/api/announcements/<int:ann_id>", methods=["PUT"])
@require_role("admin", "org_publisher", "school_admin", "ngo_officer")
def api_announcement_update(ann_id: int):
    u   = request.current_user  # type: ignore[attr-defined]
    ann = query_one("SELECT id,source_id FROM announcements WHERE id=?", (ann_id,))
    if not ann:
        return api_err("Announcement not found", 404)
    if u["role"] != "admin" and ann["source_id"] != u["id"]:
        return api_err("You can only edit your own announcements", 403)
    data = request.get_json(silent=True) or {}
    if "priority" in data and data["priority"] not in {"normal", "high", "urgent"}:
        return api_err("priority must be normal, high, or urgent")
    allowed = ["title", "body", "audience", "priority", "state", "expires_at", "attachment_url"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No fields to update")
    if u["role"] != "admin":
        sets.append("approved=0")  # edits go back through moderation
    params.append(ann_id)
    execute(f"UPDATE announcements SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Announcement updated"})

@app.route("/api/announcements/<int:ann_id>", methods=["DELETE"])
@require_role("admin", "org_publisher", "school_admin", "ngo_officer")
def api_announcement_delete(ann_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    ann = query_one("SELECT id,source_id FROM announcements WHERE id=?", (ann_id,))
    if not ann:
        return api_err("Announcement not found", 404)
    if u["role"] != "admin" and ann["source_id"] != u["id"]:
        return api_err("You are not authorised to delete this announcement", 403)
    execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    return jsonify({"message": "Announcement deleted"})


# Scholarships

@app.route("/api/scholarships")
def api_scholarships():
    deadline_after = request.args.get("deadline_after","").strip()
    search         = request.args.get("search","").strip()
    state          = request.args.get("state","").strip()
    eligibility    = request.args.get("eligibility","").strip()
    approved       = request.args.get("approved","1").strip()
    approved_val   = 0 if approved == "0" else 1
    sql = """SELECT s.id,s.title,s.description,s.eligibility,s.deadline,
                  s.how_to_apply,s.external_link,s.required_docs,
                  s.slots_available,s.whats_covered,s.contact_person,
                  s.poster_image_url,s.video_path,
                    n.org_name AS provider, n.description AS org_description,
                    n.contact AS org_contact, n.email AS org_email, n.phone AS org_phone
             FROM scholarships s LEFT JOIN ngos n ON n.id=s.ngo_id
             WHERE s.approved=?"""
    params: list = [approved_val]
    if deadline_after:
        sql += " AND s.deadline<=?"; params.append(deadline_after)
    if state:
        sql += " AND s.eligibility LIKE ?"; params.append(f"%{state}%")
    if eligibility:
        sql += " AND s.eligibility LIKE ?"; params.append(f"%{eligibility}%")
    if search:
        sql += " AND (s.title LIKE ? OR n.org_name LIKE ? OR s.description LIKE ?)"
        t = f"%{search}%"; params.extend([t, t, t])
    sql += " ORDER BY s.created_at DESC"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/scholarships/<int:scholarship_id>")
def api_scholarship_detail(scholarship_id: int):
    row = query_one(
        """SELECT s.*,n.org_name AS provider,n.description AS org_description,
                  n.contact AS org_contact,n.email AS org_email,n.phone AS org_phone
           FROM scholarships s LEFT JOIN ngos n ON n.id=s.ngo_id
           WHERE s.id=? AND s.approved=1""",
        (scholarship_id,),
    )
    if not row:
        return api_err("Scholarship not found", 404)
    return jsonify({"scholarship": row})

def _current_ngo_id(u: dict) -> int | None:
    """Resolve the calling ngo_officer's own NGO. Prefers the explicit
    users.ngo_id link (set on admin assignment or on first self-service save);
    falls back to matching by email/phone for accounts created before that
    link existed. Never matches on a blank email/phone — two accounts that
    both happen to have no phone number are not the same organisation."""
    if u.get("ngo_id"):
        return u["ngo_id"]
    email = (u.get("email") or "").strip()
    phone = (u.get("phone") or "").strip()
    if not email and not phone:
        return None
    conditions, params = [], []
    if email:
        conditions.append("email=?")
        params.append(email)
    if phone:
        conditions.append("phone=?")
        params.append(phone)
    ngo = query_one(f"SELECT id FROM ngos WHERE {' OR '.join(conditions)}", tuple(params))  # noqa: S608
    return ngo["id"] if ngo else None

@app.route("/api/scholarships", methods=["POST"])
@require_role("ngo_officer")
def api_scholarships_post():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    title    = (data.get("title") or "").strip()
    desc     = (data.get("description") or "").strip()
    elig     = (data.get("eligibility") or "").strip()
    deadline = (data.get("deadline") or "").strip()
    how      = (data.get("how_to_apply") or "").strip()
    docs     = (data.get("required_docs") or "").strip() or None
    link     = (data.get("external_link") or "").strip() or None
    if not all([title, desc, elig, deadline, how]):
        return api_err("All fields are required")
    ngo_id = _current_ngo_id(u)
    sid = execute(
        "INSERT INTO scholarships (ngo_id,title,description,eligibility,deadline,how_to_apply,required_docs,external_link,approved) VALUES (?,?,?,?,?,?,?,?,0)",
        (ngo_id, title, desc, elig, deadline, how, docs, link),
    )
    return jsonify({"message": "Scholarship submitted for review", "id": sid}), 201

@app.route("/api/scholarships/<int:scholarship_id>", methods=["PUT"])
@require_role("ngo_officer", "admin")
def api_scholarship_update(scholarship_id: int):
    u   = request.current_user  # type: ignore[attr-defined]
    sch = query_one("SELECT id,ngo_id FROM scholarships WHERE id=?", (scholarship_id,))
    if not sch:
        return api_err("Scholarship not found", 404)
    if u["role"] == "ngo_officer":
        my_ngo_id = _current_ngo_id(u)
        if not my_ngo_id or sch["ngo_id"] != my_ngo_id:
            return api_err("You can only edit your own scholarships", 403)
    data    = request.get_json(silent=True) or {}
    allowed = ["title", "description", "eligibility", "deadline", "how_to_apply",
               "required_docs", "external_link", "slots_available", "whats_covered",
               "contact_person"]
    sets, params = _build_update_clause(data, allowed)
    if not sets:
        return api_err("No fields to update")
    if u["role"] == "ngo_officer":
        sets.append("approved=0")  # edits go back through moderation
    params.append(scholarship_id)
    execute(f"UPDATE scholarships SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Scholarship updated"})

@app.route("/api/scholarships/<int:scholarship_id>", methods=["DELETE"])
@require_role("ngo_officer", "admin")
def api_scholarship_delete(scholarship_id: int):
    u   = request.current_user  # type: ignore[attr-defined]
    sch = query_one("SELECT id,ngo_id FROM scholarships WHERE id=?", (scholarship_id,))
    if not sch:
        return api_err("Scholarship not found", 404)
    if u["role"] == "ngo_officer":
        my_ngo_id = _current_ngo_id(u)
        if not my_ngo_id or sch["ngo_id"] != my_ngo_id:
            return api_err("You can only delete your own scholarships", 403)
    execute("DELETE FROM applications WHERE scholarship_id=?", (scholarship_id,))
    execute("DELETE FROM bookmarks WHERE item_type='scholarship' AND item_id=?", (scholarship_id,))
    execute("DELETE FROM scholarships WHERE id=?", (scholarship_id,))
    return jsonify({"message": "Scholarship deleted"})

def _require_own_scholarship(u: dict, scholarship_id: int):
    """Return the scholarship row, or an api_err() response if it doesn't
    exist or the caller (a non-admin ngo_officer) doesn't own it."""
    sch = query_one("SELECT id,ngo_id FROM scholarships WHERE id=?", (scholarship_id,))
    if not sch:
        return None, api_err("Scholarship not found", 404)
    if u["role"] == "ngo_officer":
        my_ngo_id = _current_ngo_id(u)
        if not my_ngo_id or sch["ngo_id"] != my_ngo_id:
            return None, api_err("You can only edit your own scholarships", 403)
    return sch, None

@app.route("/api/scholarships/<int:scholarship_id>/poster", methods=["POST"])
@require_role("ngo_officer", "admin")
def api_scholarship_poster(scholarship_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    _, err = _require_own_scholarship(u, scholarship_id)
    if err:
        return err
    if "poster" not in request.files:
        return api_err("No file uploaded")
    try:
        ext, data = _read_uploaded_image(request.files["poster"], MAX_AVATAR_BYTES)
    except ValueError as exc:
        return api_err(str(exc), 400)
    filename = f"scholarship_{scholarship_id}.{ext}"
    stored = save_file(SCHOLARSHIPS_FOLDER, filename, io.BytesIO(data))
    poster_url = _public_file_url(stored, "scholarships", filename)
    execute("UPDATE scholarships SET poster_image_url=? WHERE id=?", (poster_url, scholarship_id))
    return jsonify({"poster_image_url": poster_url})

@app.route("/api/scholarships/<int:scholarship_id>/video", methods=["POST"])
@require_role("ngo_officer", "admin")
def api_scholarship_video(scholarship_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    _, err = _require_own_scholarship(u, scholarship_id)
    if err:
        return err
    if "video" not in request.files:
        return api_err("No file uploaded")
    f = request.files["video"]
    if not f.filename:
        return api_err("Empty filename")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in VIDEO_EXTENSIONS:
        return api_err("Only MP4, WebM, OGG, or M4V files are allowed")
    if not _is_valid_video(f.stream):
        return api_err("File content does not match a recognised video format", 400)
    data = f.stream.read()
    if len(data) > MAX_MATERIAL_BYTES:
        return api_err(f"File must be under {MAX_MATERIAL_BYTES // (1024 * 1024)} MB")
    safe_name = f"scholarship_{scholarship_id}.{ext}"
    stored = save_file(SCHOLARSHIPS_FOLDER, safe_name, io.BytesIO(data))
    video_path = _public_file_url(stored, "scholarships", safe_name)
    execute("UPDATE scholarships SET video_path=? WHERE id=?", (video_path, scholarship_id))
    return jsonify({"video_path": video_path})

# Applications

@app.route("/api/applications")
@require_auth
def api_applications():
    u = request.current_user  # type: ignore[attr-defined]
    rows = query_all(
        """SELECT a.id,a.scholarship_id,a.status,a.note,a.applied_at,a.updated_at,
                  s.title,s.deadline,n.org_name AS provider
           FROM applications a
           JOIN scholarships s ON s.id=a.scholarship_id
           LEFT JOIN ngos n ON n.id=s.ngo_id
           WHERE a.user_id=?
           ORDER BY a.applied_at DESC""",
        (u["id"],),
    )
    return jsonify({"items": rows})

@app.route("/api/applications", methods=["POST"])
@require_auth
def api_applications_submit():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    scholarship_id = data.get("scholarship_id")
    note           = (data.get("note") or "").strip() or None
    if not scholarship_id:
        return api_err("scholarship_id is required")
    sch = query_one("SELECT id,deadline FROM scholarships WHERE id=? AND approved=1", (int(scholarship_id),))
    if not sch:
        return api_err("Scholarship not found", 404)
    existing = query_one("SELECT id FROM applications WHERE user_id=? AND scholarship_id=?", (u["id"], int(scholarship_id)))
    if existing:
        return api_err("You have already applied for this scholarship", 409)
    aid = execute(
        "INSERT INTO applications (user_id,scholarship_id,status,note) VALUES (?,?,?,?)",
        (u["id"], int(scholarship_id), "submitted", note),
    )
    return jsonify({"message": "Application submitted", "id": aid}), 201

@app.route("/api/applications/<int:app_id>", methods=["DELETE"])
@require_auth
def api_application_withdraw(app_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    app_row = query_one("SELECT id,status FROM applications WHERE id=? AND user_id=?", (app_id, u["id"]))
    if not app_row:
        return api_err("Application not found", 404)
    if app_row["status"] not in ("submitted",):
        return api_err("Only submitted applications can be withdrawn")
    execute("UPDATE applications SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE id=?", (app_id,))
    return jsonify({"message": "Application withdrawn"})

@app.route("/api/admin/applications/<int:app_id>/status", methods=["POST"])
@require_role("admin")
def api_admin_update_application(app_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    valid_statuses = {"submitted","under_review","shortlisted","successful","unsuccessful"}
    if status not in valid_statuses:
        return api_err(f"status must be one of: {', '.join(valid_statuses)}")
    execute("UPDATE applications SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, app_id))
    log_audit(u["id"], f"set_status_{status}", "application", app_id)
    app_row = query_one(
        """SELECT a.*, u.email AS applicant_email, u.name AS applicant_name,
                  u.notify_email, s.title AS scholarship_title
           FROM applications a
           JOIN users u ON u.id=a.user_id
           JOIN scholarships s ON s.id=a.scholarship_id
           WHERE a.id=?""",
        (app_id,),
    )
    if app_row:
        label = status.replace("_", " ").title()
        create_notification(
            app_row["user_id"], "application_status",
            f"Application update: {app_row['scholarship_title']}",
            f"Status changed to {label}",
            ref_type="application", ref_id=app_id,
        )
        if app_row.get("applicant_email") and app_row.get("notify_email"):
            send_email(
                app_row["applicant_email"],
                f"EduPortal — Application Update: {app_row['scholarship_title']}",
                f"Dear {app_row['applicant_name']},\n\nYour application for \"{app_row['scholarship_title']}\" has been updated to: {label}.\n\nLog in to EduPortal South Sudan to view details.\n\nEduPortal South Sudan",
            )
    return jsonify({"message": f"Application status updated to {status}"})

# Bookmarks

@app.route("/api/bookmarks/detailed")
@require_auth
def api_bookmarks_detailed():
    """Returns bookmarks with full item details — one query per type, no N+1."""
    u = request.current_user  # type: ignore[attr-defined]
    bms = query_all(
        "SELECT id, item_type, item_id, saved_at FROM bookmarks WHERE user_id=? ORDER BY saved_at DESC",
        (u["id"],),
    )
    school_ids      = [b["item_id"] for b in bms if b["item_type"] == "school"]
    material_ids    = [b["item_id"] for b in bms if b["item_type"] == "material"]
    scholarship_ids = [b["item_id"] for b in bms if b["item_type"] == "scholarship"]

    def fetch_by_ids(table: str, cols: str, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = query_all(f"SELECT {cols} FROM {table} WHERE id IN ({placeholders})", tuple(ids))  # noqa: S608
        return {r["id"]: r for r in rows}

    schools     = fetch_by_ids("schools",     "id,name,state,county,level,boarding,status,description,enrollment", school_ids)
    materials   = fetch_by_ids("materials",   "id,title,subject,grade,`year`,type,file_size,preview_text,file_path", material_ids)
    scholarship_rows = query_all(
        f"""SELECT s.id,s.title,s.description,s.eligibility,s.deadline,s.how_to_apply,
                   n.org_name AS provider
            FROM scholarships s LEFT JOIN ngos n ON n.id=s.ngo_id
            WHERE s.id IN ({','.join('?'*len(scholarship_ids)) if scholarship_ids else 'NULL'})""",  # noqa: S608
        tuple(scholarship_ids),
    ) if scholarship_ids else []
    sch_map = {r["id"]: r for r in scholarship_rows}

    enriched = []
    for b in bms:
        detail: dict | None = None
        if b["item_type"] == "school":
            detail = schools.get(b["item_id"])
        elif b["item_type"] == "material":
            detail = materials.get(b["item_id"])
        elif b["item_type"] == "scholarship":
            detail = sch_map.get(b["item_id"])
        enriched.append({
            "bookmark_id": b["id"],
            "item_type":   b["item_type"],
            "item_id":     b["item_id"],
            "saved_at":    b["saved_at"],
            "detail":      detail,
        })
    return jsonify({"items": enriched})


@app.route("/api/bookmarks", methods=["GET","POST"])
@require_auth
def api_bookmarks():
    u = request.current_user  # type: ignore[attr-defined]
    if request.method == "GET":
        return jsonify({"items": query_all(
            "SELECT id,item_type,item_id,saved_at FROM bookmarks WHERE user_id=? ORDER BY saved_at DESC",
            (u["id"],))})
    if u["role"] == "parent":
        return api_err("Parent accounts can search and view but not save bookmarks", 403)
    data      = request.get_json(silent=True) or {}
    item_type = (data.get("item_type") or "").strip()
    item_id   = data.get("item_id")
    if item_type not in {"school","material","scholarship"}:
        return api_err("Invalid item_type")
    if item_id is None:
        return api_err("item_id required")
    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
        return api_err("item_id must be a number")
    ignore_kw = "INSERT IGNORE" if is_mysql() else "INSERT OR IGNORE"
    execute(
        f"""{ignore_kw} INTO bookmarks (user_id,item_type,item_id)
           VALUES (?,?,?)""",
        (u["id"], item_type, item_id),
    )
    return jsonify({"message": "Saved"})

@app.route("/api/bookmarks/<int:bookmark_id>", methods=["DELETE"])
@require_auth
def api_bookmark_delete(bookmark_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    execute("DELETE FROM bookmarks WHERE id=? AND user_id=?", (bookmark_id, u["id"]))
    return jsonify({"message": "Removed"})


# Admin

@app.route("/api/admin/queue")
@require_role("admin")
def api_admin_queue():
    mat_items = query_all(
        "SELECT * FROM materials WHERE approved=0 ORDER BY created_at DESC")
    ann_items = query_all(
        "SELECT * FROM announcements WHERE approved=0 ORDER BY created_at DESC")
    sch_items = query_all(
        """SELECT s.*, n.org_name AS provider
           FROM scholarships s LEFT JOIN ngos n ON n.id=s.ngo_id
           WHERE s.approved=0 ORDER BY s.created_at DESC""")
    school_items = query_all(
        "SELECT * FROM schools WHERE approved=0 ORDER BY created_at DESC")
    ngo_items = query_all(
        "SELECT * FROM ngos WHERE verified=0 ORDER BY id DESC")
    org_items = query_all(
        "SELECT * FROM organizations WHERE verified=0 ORDER BY id DESC")
    return jsonify({
        "materials":     len(mat_items),
        "announcements": len(ann_items),
        "scholarships":  len(sch_items),
        "schools":       len(school_items),
        "ngos":          len(ngo_items),
        "organizations": len(org_items),
        "material_items":     [{**r, "title":r["title"],"meta":f"{r['subject']} · {r['grade']} · {r['year']} · {r['type']}"} for r in mat_items],
        "announcement_items": [{**r, "title":r["title"],"meta":f"{r['source_type']} · {r['audience']} · expires {r['expires_at']}"} for r in ann_items],
        "scholarship_items":  [{**r, "title":r["title"],"meta":f"{r['provider']} · deadline {r['deadline']}"} for r in sch_items],
        "school_items":       [{**r, "title":r["name"],"meta":f"{r['county']}, {r['state']} · {r['level']}"} for r in school_items],
        "ngo_items":          [{**r, "title":r["org_name"],"meta":f"{r['org_type'] or 'NGO'} · {r['county'] or ''}, {r['state'] or ''}"} for r in ngo_items],
        "organization_items": [{**r, "title":r["name"],"meta":f"{r['org_type'] or 'Organisation'} · {r['state'] or 'National'}"} for r in org_items],
    })

@app.route("/api/admin/approve", methods=["POST"])
@require_role("admin")
def api_admin_approve():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    target_type = (data.get("target_type") or "").strip()
    target_id   = data.get("target_id")
    action      = (data.get("action") or "approve").strip()
    note        = (data.get("note") or "").strip()
    # (table, flag column) — ngos uses `verified` instead of `approved`
    table_map = {
        "material":     ("materials", "approved"),
        "announcement": ("announcements", "approved"),
        "scholarship":  ("scholarships", "approved"),
        "school":       ("schools", "approved"),
        "ngo":          ("ngos", "verified"),
        "organization": ("organizations", "verified"),
    }
    if target_type not in table_map or not target_id:
        return api_err("target_type and target_id required")
    table, flag_col = table_map[target_type]
    val = 1 if action == "approve" else 0
    execute(f"UPDATE {table} SET {flag_col}=? WHERE id=?", (val, int(target_id)))  # noqa: S608
    if action != "approve" and note and target_type in {"scholarship", "school", "material", "announcement"}:
        execute(f"UPDATE {table} SET rejection_reason=? WHERE id=?", (note, int(target_id)))  # noqa: S608
    log_audit(u["id"], action, target_type, int(target_id), note)
    past_tense = "rejected" if action == "reject" else f"{action}d"
    return jsonify({"message": f"{target_type} {past_tense}"})

@app.route("/api/admin/users")
@require_role("admin")
def api_admin_users():
    role = request.args.get("role","").strip()
    sql  = "SELECT id,name,email,phone,role,state,county,verified,created_at,school_id FROM users WHERE 1=1"
    params: list = []
    sql = _append_equals_filters(sql, params, [(role, "role")])
    sql += " ORDER BY created_at DESC"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/admin/applications")
@require_role("admin")
def api_admin_all_applications():
    status = request.args.get("status", "").strip()
    sql = """
        SELECT a.id, a.user_id, a.scholarship_id, a.status, a.note, a.applied_at, a.updated_at,
               u.name AS applicant_name, u.email AS applicant_email,
               s.title AS scholarship_title, s.deadline
        FROM applications a
        JOIN users u ON u.id = a.user_id
        JOIN scholarships s ON s.id = a.scholarship_id
        WHERE 1=1
    """
    params: list = []
    sql = _append_equals_filters(sql, params, [(status, "a.status")])
    sql += " ORDER BY a.applied_at DESC"
    return jsonify({"items": query_all(sql, tuple(params))})


@app.route("/api/admin/users/<int:user_id>/assign-school", methods=["POST"])
@require_role("admin")
def api_admin_assign_school(user_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    school_id = data.get("school_id")  # None to unassign
    target = query_one("SELECT id,role FROM users WHERE id=?", (user_id,))
    if not target:
        return api_err("User not found", 404)
    if target["role"] != "school_admin":
        return api_err("Only school_admin users can be assigned to a school")
    if school_id is not None:
        school = query_one("SELECT id FROM schools WHERE id=?", (int(school_id),))
        if not school:
            return api_err("School not found", 404)
    execute("UPDATE users SET school_id=? WHERE id=?", (int(school_id) if school_id else None, user_id))
    log_audit(u["id"], "assign_school", "user", user_id, f"school_id={school_id}")
    return jsonify({"message": "School assigned"})

@app.route("/api/admin/users/<int:user_id>/assign-ngo", methods=["POST"])
@require_role("admin")
def api_admin_assign_ngo(user_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    ngo_id = data.get("ngo_id")  # None to unassign
    target = query_one("SELECT id,role FROM users WHERE id=?", (user_id,))
    if not target:
        return api_err("User not found", 404)
    if target["role"] != "ngo_officer":
        return api_err("Only ngo_officer users can be assigned to an organisation")
    if ngo_id is not None:
        ngo = query_one("SELECT id FROM ngos WHERE id=?", (int(ngo_id),))
        if not ngo:
            return api_err("Organisation not found", 404)
    execute("UPDATE users SET ngo_id=? WHERE id=?", (int(ngo_id) if ngo_id else None, user_id))
    log_audit(u["id"], "assign_ngo", "user", user_id, f"ngo_id={ngo_id}")
    return jsonify({"message": "Organisation assigned"})

@app.route("/api/admin/pending-assignments")
@require_role("admin")
def api_admin_pending_assignments():
    """school_admin / ngo_officer accounts with no school/organisation linked
    yet — they can't do anything useful until assigned (or self-service-linked
    via the claim flow), so surface them for an admin to resolve."""
    unassigned_school_admins = query_all(
        "SELECT id,name,email,phone,state,county,created_at FROM users "
        "WHERE role='school_admin' AND school_id IS NULL ORDER BY created_at DESC")
    unassigned_ngo_officers = query_all(
        "SELECT id,name,email,phone,state,county,created_at FROM users "
        "WHERE role='ngo_officer' AND ngo_id IS NULL ORDER BY created_at DESC")
    return jsonify({
        "school_admins": unassigned_school_admins,
        "ngo_officers":  unassigned_ngo_officers,
    })

@app.route("/api/admin/backup-status")
@require_role("admin")
def api_admin_backup_status():
    items = query_all("SELECT id,ran_at,success,file_path,file_size,message FROM backup_runs ORDER BY ran_at DESC LIMIT 20")
    return jsonify({"items": items})

@app.route("/api/admin/ngos")
@require_role("admin")
def api_admin_ngos():
    items = query_all(
        "SELECT id,org_name,org_type,contact,email,phone,state,county,verified,registration_verified "
        "FROM ngos ORDER BY org_name")
    return jsonify({"items": items})

@app.route("/api/admin/ngos/<int:ngo_id>", methods=["DELETE"])
@require_role("admin")
def api_admin_ngo_delete(ngo_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    ngo = query_one("SELECT id FROM ngos WHERE id=?", (ngo_id,))
    if not ngo:
        return api_err("Organisation not found", 404)
    execute("DELETE FROM ngo_programs WHERE ngo_id=?", (ngo_id,))
    execute("DELETE FROM scholarships WHERE ngo_id=?", (ngo_id,))
    execute("UPDATE users SET ngo_id=NULL WHERE ngo_id=?", (ngo_id,))
    execute("DELETE FROM ngos WHERE id=?", (ngo_id,))
    log_audit(u["id"], "delete_ngo", "ngo", ngo_id)
    return jsonify({"message": "Organisation deleted"})

@app.route("/api/admin/registration-verify", methods=["POST"])
@require_role("admin")
def api_admin_registration_verify():
    """Manual attestation that a school/NGO's registration_number has been
    checked — not a live government-registry lookup (none exists to
    integrate with)."""
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    target_type = (data.get("target_type") or "").strip()
    target_id   = data.get("target_id")
    verified    = 1 if data.get("verified", True) else 0
    table_map = {"school": "schools", "ngo": "ngos"}
    if target_type not in table_map or not target_id:
        return api_err("target_type must be 'school' or 'ngo', and target_id is required")
    table = table_map[target_type]
    row = query_one(f"SELECT id FROM {table} WHERE id=?", (int(target_id),))  # noqa: S608
    if not row:
        return api_err(f"{target_type.capitalize()} not found", 404)
    execute(f"UPDATE {table} SET registration_verified=? WHERE id=?", (verified, int(target_id)))  # noqa: S608
    log_audit(u["id"], "registration_verify" if verified else "registration_unverify", target_type, int(target_id))
    return jsonify({"message": f"Registration {'verified' if verified else 'unverified'}"})

@app.route("/api/admin/users/<int:user_id>/suspend", methods=["POST"])
@require_role("admin")
def api_admin_suspend(user_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    if user_id == u["id"]:
        return api_err("Cannot suspend your own account")
    execute("UPDATE users SET verified=-1 WHERE id=?", (user_id,))
    log_audit(u["id"], "suspend", "user", user_id)
    return jsonify({"message": "User suspended"})

@app.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
@require_role("admin")
def api_admin_reset_password(user_id: int):
    """Admin-initiated reset — generates a token via the same password_resets
    mechanism as the self-service /api/forgot-password flow and emails/SMS it."""
    u = request.current_user  # type: ignore[attr-defined]
    target = query_one("SELECT id,email,phone,name,notify_email FROM users WHERE id=?", (user_id,))
    if not target:
        return api_err("User not found", 404)
    token = _create_password_reset_token(target["id"])
    reset_msg = (
        f"Dear {target['name']},\n\nAn administrator has initiated a password reset for your "
        f"EduPortal South Sudan account.\n\nYour reset code is: {token}\n\nThis code expires in 1 hour."
    )
    email_sent = sms_sent = False
    if target.get("email") and target.get("notify_email"):
        email_sent = send_email(target["email"], "EduPortal — Password Reset Requested by Admin", reset_msg)
    if not email_sent and target.get("phone"):
        sms_sent = send_sms(target["phone"], f"EduPortal admin-initiated reset code: {token} (expires 1hr)")
    log_audit(u["id"], "admin_reset_password", "user", user_id)
    response: dict = {"message": "Reset code generated and sent to the user."}
    if not email_sent and not sms_sent:
        response["dev_token"] = token
        response["note"] = "Configure SMTP_HOST or AT_API_KEY env vars to send via email/SMS in production."
    return jsonify(response)

@app.route("/api/admin/users/<int:user_id>/unsuspend", methods=["POST"])
@require_role("admin")
def api_admin_unsuspend(user_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    target = query_one("SELECT id FROM users WHERE id=?", (user_id,))
    if not target:
        return api_err("User not found", 404)
    execute("UPDATE users SET verified=1 WHERE id=?", (user_id,))
    log_audit(u["id"], "unsuspend", "user", user_id)
    return jsonify({"message": "User reactivated"})

@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@require_role("admin")
def api_admin_edit_user(user_id: int):
    """General account-details edit for the platform admin (FR 7.2)."""
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    target = query_one("SELECT id FROM users WHERE id=?", (user_id,))
    if not target:
        return api_err("User not found", 404)
    allowed = ["name", "email", "phone", "state", "county"]
    sets, params = _build_update_clause(data, allowed, transform=lambda v: (v or "").strip() or None)
    if not sets:
        return api_err("No updatable fields provided")
    params.append(user_id)
    execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    log_audit(u["id"], "edit_user", "user", user_id, ", ".join(sets))
    return jsonify({"message": "User updated"})

@app.route("/api/admin/users/<int:user_id>/role", methods=["POST"])
@require_role("admin")
def api_admin_change_role(user_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip()
    valid_roles = {"student","parent","teacher","school_admin","ngo_officer","org_publisher","admin"}
    if new_role not in valid_roles:
        return api_err(f"role must be one of: {', '.join(valid_roles)}")
    if user_id == u["id"] and new_role != "admin":
        return api_err("Cannot change your own role away from admin")
    execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
    log_audit(u["id"], f"change_role_to_{new_role}", "user", user_id)
    return jsonify({"message": f"Role changed to {new_role}"})

@app.route("/api/admin/audit-log")
@require_role("admin")
def api_audit_log():
    action    = request.args.get("action", "").strip()
    admin_id  = request.args.get("admin_id", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to", "").strip()
    sql = (
        "SELECT a.id,a.admin_id,a.action,a.target_type,a.target_id,a.note,a.timestamp,"
        "u.name AS admin_name "
        "FROM audit_log a LEFT JOIN users u ON u.id=a.admin_id WHERE 1=1"
    )
    params: list = []
    sql = _append_equals_filters(sql, params, [(action, "a.action")])
    if admin_id:
        sql += " AND a.admin_id=?"; params.append(int(admin_id))
    if date_from:
        sql += " AND date(a.timestamp) >= date(?)"; params.append(date_from)
    if date_to:
        sql += " AND date(a.timestamp) <= date(?)"; params.append(date_to)
    sql += " ORDER BY a.timestamp DESC LIMIT 200"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/admin/analytics")
@require_role("admin")
def api_admin_analytics():
    users_by_state = query_all(
        "SELECT COALESCE(state,'Unknown') AS state, COUNT(*) AS count FROM users GROUP BY COALESCE(state,'Unknown') ORDER BY count DESC")
    users_by_role = query_all(
        "SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC")
    bookmarked_schools = query_all(
        """SELECT s.name,COUNT(*) AS count FROM bookmarks b
           JOIN schools s ON s.id=b.item_id WHERE b.item_type='school'
           GROUP BY s.id,s.name ORDER BY count DESC LIMIT 5""")
    bookmarked_scholarships = query_all(
        """SELECT s.title AS name,COUNT(*) AS count FROM bookmarks b
           JOIN scholarships s ON s.id=b.item_id WHERE b.item_type='scholarship'
           GROUP BY s.id,s.title ORDER BY count DESC LIMIT 5""")
    top_materials = query_all(
        """SELECT m.title,m.subject,m.grade,m.download_count AS downloads,COUNT(b.id) AS saves
           FROM materials m LEFT JOIN bookmarks b ON b.item_id=m.id AND b.item_type='material'
           WHERE m.approved=1 GROUP BY m.id ORDER BY m.download_count DESC, saves DESC LIMIT 5""")
    most_viewed_announcements = query_all(
        """SELECT title, view_count FROM announcements
           WHERE approved=1 ORDER BY view_count DESC, created_at DESC LIMIT 5""")
    total_downloads = count("SELECT COALESCE(SUM(download_count),0) AS count FROM materials")
    app_counts = query_all(
        """SELECT s.title,COUNT(a.id) AS applications
           FROM scholarships s LEFT JOIN applications a ON a.scholarship_id=s.id
           WHERE s.approved=1 GROUP BY s.id ORDER BY applications DESC LIMIT 5""")
    return jsonify({
        "users_by_state":    users_by_state,
        "users_by_role":     users_by_role,
        "bookmarked_schools": bookmarked_schools,
        "bookmarked_scholarships": bookmarked_scholarships,
        "top_materials":     top_materials,
        "most_viewed_announcements": most_viewed_announcements,
        "scholarship_applications": app_counts,
        "approved": {
            "materials":     count("SELECT COUNT(*) AS count FROM materials WHERE approved=1"),
            "announcements": count("SELECT COUNT(*) AS count FROM announcements WHERE approved=1"),
            "scholarships":  count("SELECT COUNT(*) AS count FROM scholarships WHERE approved=1"),
            "schools":       count("SELECT COUNT(*) AS count FROM schools WHERE approved=1"),
        },
        "total_users": count("SELECT COUNT(*) AS count FROM users"),
        "total_applications": count("SELECT COUNT(*) AS count FROM applications"),
        "total_downloads": total_downloads,
    })

@app.route("/api/admin/analytics/export.csv")
@require_role("admin")
def api_admin_analytics_export():
    import csv
    import io as _io
    buf = _io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Users by state"])
    writer.writerow(["State", "Count"])
    for row in query_all("SELECT COALESCE(state,'Unknown') AS state, COUNT(*) AS count FROM users GROUP BY COALESCE(state,'Unknown') ORDER BY count DESC"):
        writer.writerow([row["state"], row["count"]])
    writer.writerow([])

    writer.writerow(["Users by role"])
    writer.writerow(["Role", "Count"])
    for row in query_all("SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC"):
        writer.writerow([row["role"], row["count"]])
    writer.writerow([])

    writer.writerow(["Approved content totals"])
    writer.writerow(["Type", "Count"])
    for label, table in [("Materials", "materials"), ("Announcements", "announcements"),
                          ("Scholarships", "scholarships"), ("Schools", "schools")]:
        writer.writerow([label, count(f"SELECT COUNT(*) AS count FROM {table} WHERE approved=1")])  # noqa: S608

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=eduportal_analytics.csv"},
    )

# Notification test routes

@app.route("/api/notifications/test-email", methods=["POST"])
@require_role("admin")
def api_test_email():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    to   = (data.get("to") or u.get("email") or "").strip()
    if not to:
        return api_err("No recipient email address")
    sent = send_email(to, "EduPortal Test Email", "This is a test email from EduPortal South Sudan.")
    return jsonify({"sent": sent, "message": "Email sent" if sent else "SMTP not configured — set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"})


@app.route("/api/notifications/test-sms", methods=["POST"])
@require_role("admin")
def api_test_sms():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    to   = (data.get("to") or u.get("phone") or "").strip()
    if not to:
        return api_err("No recipient phone number")
    sent = send_sms(to, "EduPortal South Sudan: This is a test SMS notification.")
    return jsonify({"sent": sent, "message": "SMS sent" if sent else "Africa's Talking not configured — set AT_API_KEY in .env"})


# Health

# Forgot / Reset Password

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot-password.html")

@app.route("/api/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def api_forgot_password():
    """Generates a reset token stored in DB. In production send via SMS/email."""
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    if not identifier:
        return api_err("Phone number or email is required")
    id_lower = identifier.lower()
    id_phone = identifier.replace(" ", "")
    user = query_one(
        "SELECT * FROM users WHERE lower(email)=? OR replace(phone,' ','')=?",
        (id_lower, id_phone),
    )
    # Always return success to avoid user enumeration
    if user:
        token = _create_password_reset_token(user["id"])
        # Send via email if available, SMS if not
        email_sent = sms_sent = False
        reset_msg = f"Your EduPortal password reset code is: {token}\n\nThis code expires in 1 hour."
        if user.get("email"):
            email_sent = send_email(user["email"], "EduPortal — Password Reset Code", reset_msg)
        if not email_sent and user.get("phone"):
            sms_sent = send_sms(user["phone"], f"EduPortal reset code: {token} (expires 1hr)")
        response: dict = {"message": "Reset code sent."}
        # In dev (no SMTP/SMS configured) expose token directly so it can be used
        if not email_sent and not sms_sent:
            response["dev_token"] = token
            response["user_id"]   = user["id"]
            response["note"]      = "Configure SMTP_HOST or AT_API_KEY env vars to send via email/SMS in production."
        return jsonify(response)
    return jsonify({"message": "If that account exists, a reset code has been sent."})

@app.route("/api/reset-password", methods=["POST"])
def api_reset_password():
    data     = request.get_json(silent=True) or {}
    user_id  = data.get("user_id")
    token    = (data.get("token") or "").strip()
    new_pass = (data.get("new_password") or "").strip()
    if not all([user_id, token, new_pass]):
        return api_err("user_id, token, and new_password are required")
    if len(new_pass) < 8:
        return api_err("Password must be at least 8 characters")
    try:
        user_id_int = int(str(user_id))
    except (TypeError, ValueError):
        return api_err("user_id must be a number")
    row = query_one(
        "SELECT * FROM password_resets WHERE user_id=? AND token=?",
        (user_id_int, token),
    )
    if not row:
        return api_err("Invalid or expired reset token", 400)
    created_at = parse_utc_iso(row.get("created_at"))
    if created_at is None or datetime.now(timezone.utc) - created_at > timedelta(hours=1):
        return api_err("Invalid or expired reset token", 400)
    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    execute("UPDATE users SET password_hash=?, has_password=1 WHERE id=?", (new_hash, user_id_int))
    execute("DELETE FROM password_resets WHERE user_id=?", (user_id_int,))
    return jsonify({"message": "Password reset successfully. You can now sign in."})

# Notifications (bell)

@app.route("/api/notifications")
@require_auth
def api_notifications():
    u = request.current_user  # type: ignore[attr-defined]
    now_utc = datetime.now(timezone.utc)
    next_week = (now_utc + timedelta(days=7)).date().isoformat()
    recent_cutoff = (now_utc - timedelta(days=7)).isoformat()

    persisted = query_all(
        "SELECT id,type,title,body,`read`,created_at,ref_type,ref_id FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
        (u["id"],),
    )
    deadlines = query_all(
        """SELECT s.id, s.title, s.deadline
           FROM scholarships s
           JOIN applications a ON a.scholarship_id=s.id
           WHERE a.user_id=? AND s.approved=1
             AND CAST(s.deadline AS DATE) >= CURRENT_DATE
             AND CAST(s.deadline AS DATE) <= CAST(? AS DATE)
           ORDER BY s.deadline ASC""",
        (u["id"], next_week),
    )
    ann = query_all(
        "SELECT id,title,created_at FROM announcements WHERE approved=1 AND created_at >= ? ORDER BY created_at DESC LIMIT 5",
        (recent_cutoff,),
    )

    items = [
        {"id": n["id"], "type": n["type"], "title": n["title"], "body": n["body"],
         "read": bool(n["read"]), "persisted": True,
         "ref_type": n["ref_type"], "ref_id": n["ref_id"]}
        for n in persisted
    ]
    for r in deadlines:
        items.append({"type": "deadline", "title": f"Deadline soon: {r['title']}", "body": f"Closes {r['deadline']}", "id": r["id"], "read": True, "persisted": False, "ref_type": "scholarship", "ref_id": r["id"]})
    for a in ann:
        items.append({"type": "announcement", "title": a["title"], "body": str(a["created_at"])[:10], "id": a["id"], "read": True, "persisted": False, "ref_type": "announcement", "ref_id": a["id"]})

    unread = sum(1 for n in persisted if not n["read"])
    return jsonify({"items": items, "count": unread})

@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@require_auth
def api_notification_mark_read(notif_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    row = query_one("SELECT id FROM notifications WHERE id=? AND user_id=?", (notif_id, u["id"]))
    if not row:
        return api_err("Notification not found", 404)
    execute("UPDATE notifications SET `read`=1 WHERE id=?", (notif_id,))
    return jsonify({"message": "Marked as read"})

@app.route("/api/notifications/read-all", methods=["POST"])
@require_auth
def api_notifications_mark_all_read():
    u = request.current_user  # type: ignore[attr-defined]
    execute("UPDATE notifications SET `read`=1 WHERE user_id=? AND `read`=0", (u["id"],))
    return jsonify({"message": "All notifications marked as read"})

@app.route("/api/notifications/stream")
def api_notifications_stream():
    """Server-sent events: push new notifications to the browser as they're created."""
    token = (request.args.get("token") or "").strip()
    user = None
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user = query_one("SELECT * FROM users WHERE id=?", (payload["sub"],))
        except jwt.PyJWTError:
            user = None
    if not user:
        return api_err("Authentication required", 401)

    user_id = user["id"]

    def event_stream():
        import json
        q = subscribe(user_id)
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    payload = q.get(timeout=25)
                    yield f"data: {json.dumps(payload)}\n\n"
                except Empty:
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            pass
        finally:
            unsubscribe(user_id, q)

    return Response(event_stream(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })

# Web Push

@app.route("/api/push/vapid-public-key")
def api_push_vapid_public_key():
    return jsonify({"key": VAPID_PUBLIC_KEY, "enabled": push_is_configured()})

@app.route("/api/push/subscribe", methods=["POST"])
@require_auth
def api_push_subscribe():
    u = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth_key = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth_key:
        return api_err("endpoint and keys.p256dh/keys.auth are required")
    if is_mysql():
        push_sql = """INSERT INTO push_subscriptions (user_id,endpoint,p256dh,auth) VALUES (?,?,?,?)
                      ON DUPLICATE KEY UPDATE
                      user_id=VALUES(user_id), p256dh=VALUES(p256dh), auth=VALUES(auth)"""
    else:
        push_sql = """INSERT INTO push_subscriptions (user_id,endpoint,p256dh,auth) VALUES (?,?,?,?)
                      ON CONFLICT (endpoint) DO UPDATE SET
                      user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth"""
    execute(push_sql, (u["id"], endpoint, p256dh, auth_key))
    return jsonify({"message": "Subscribed to push notifications"})

@app.route("/api/push/unsubscribe", methods=["POST"])
@require_auth
def api_push_unsubscribe():
    u = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    if not endpoint:
        return api_err("endpoint is required")
    execute("DELETE FROM push_subscriptions WHERE endpoint=? AND user_id=?", (endpoint, u["id"]))
    return jsonify({"message": "Unsubscribed"})

# Admin: onboard school (create + send invite email)

@app.route("/api/admin/onboard-school", methods=["POST"])
@require_role("admin")
def api_admin_onboard_school():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    name    = (data.get("name") or "").strip()[:150]
    state   = (data.get("state") or "").strip()[:80]
    county  = (data.get("county") or "").strip()[:80]
    level   = (data.get("level") or "").strip()
    email   = (data.get("email") or "").strip()[:120] or None
    if not all([name, state, county, level]):
        return api_err("name, state, county, and level are required")
    if level not in {"primary", "secondary", "tertiary", "both"}:
        return api_err("level must be primary, secondary, tertiary, or both")
    if not email:
        return api_err("A contact email is required to send the admin invitation")
    sid = execute(
        """INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,
           email,capacity,status,enrollment,language,boarding,ownership,hours,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name, state, county, level,
            (data.get("type") or "mixed").strip(),
            (data.get("curriculum") or "National").strip(),
            (data.get("contact_name") or "").strip()[:100],
            (data.get("phone") or "").strip()[:30],
            email,
            data.get("capacity") or None,
            (data.get("status") or "open").strip(),
            data.get("enrollment") or 0,
            (data.get("language") or "English").strip(),
            (data.get("boarding") or "Day").strip(),
            (data.get("ownership") or "public").strip(),
            (data.get("hours") or "").strip()[:80] or None,
            (data.get("description") or "").strip() or None,
        ),
    )
    result = _onboard_and_invite(
        u["id"], "create_school", "school", sid, "school_admin", email,
        invite_verb=f"manage {name}",
        account_label="admin account",
        invite_note="This link is single-use. If you did not expect this email, please ignore it.",
        subject_label=f"Admin Invitation for {name}",
    )
    return jsonify({"message": "School created and invitation sent", **result}), 201


@app.route("/api/admin/onboard-ngo", methods=["POST"])
@require_role("admin")
def api_admin_onboard_ngo():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    org_name    = (data.get("org_name") or "").strip()[:150]
    contact     = (data.get("contact") or "").strip()[:100]
    email       = (data.get("email") or "").strip()[:120] or None
    phone       = (data.get("phone") or "").strip()[:30] or None
    description = (data.get("description") or "").strip() or None
    if not org_name or not email:
        return api_err("org_name and email are required")
    ngo_id = execute(
        "INSERT INTO ngos (org_name,contact,email,phone,description,verified) VALUES (?,?,?,?,?,1)",
        (org_name, contact, email, phone, description),
    )
    result = _onboard_and_invite(
        u["id"], "create_ngo", "ngo", ngo_id, "ngo_officer", email,
        invite_verb=f"manage {org_name}",
        account_label="admin account",
        invite_note="This link is single-use. If you did not expect this email, please ignore it.",
        subject_label=f"Admin Invitation for {org_name}",
    )
    return jsonify({"message": "Organisation created and invitation sent", **result}), 201


@app.route("/accept-invite")
def accept_invite_page():
    return render_template("accept-invite.html")


@app.route("/api/accept-invite", methods=["POST"])
@limiter.limit("10 per minute")
def api_accept_invite():
    data     = request.get_json(silent=True) or {}
    token    = (data.get("token") or "").strip()
    name     = (data.get("name") or "").strip()[:120]
    password = (data.get("password") or "").strip()
    if not all([token, name, password]):
        return api_err("token, name, and password are required")
    if len(password) < 8:
        return api_err("Password must be at least 8 characters")
    # Look up by hint first (fast index scan), then bcrypt-verify the full token
    hint = token[:8]
    candidates = query_one(
        "SELECT * FROM invitations WHERE token_hint=? AND used=0",
        (hint,),
    )
    inv = None
    if candidates:
        try:
            if bcrypt.checkpw(token.encode(), candidates["token_hash"].encode()):
                inv = candidates
        except Exception:
            pass
    if not inv:
        return api_err("Invalid or already-used invitation link", 400)
    # Check if a user with this email already exists
    existing = query_one("SELECT id FROM users WHERE email=?", (inv["email"],))
    if existing:
        return api_err("An account with this email already exists. Please sign in.", 409)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    uid = execute(
        "INSERT INTO users (name,email,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,1)",
        (name, inv["email"], pw_hash, inv["role"], "", ""),
    )
    # Link user to their school, NGO, or org
    if inv["role"] == "school_admin" and inv["ref_id"]:
        execute("UPDATE users SET school_id=? WHERE id=?", (inv["ref_id"], uid))
    # Mark invitation as used
    execute("UPDATE invitations SET used=1 WHERE id=?", (inv["id"],))
    user = query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not user:
        return api_err("Account creation failed", 500)
    return jsonify({
        "token": make_token(user),
        "refresh_token": make_refresh_token(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"], "school_id": user["school_id"], "ngo_id": user["ngo_id"], "avatar": user["avatar"] or None},
    }), 201


@app.route("/api/invitations/check")
def api_invitation_check():
    """Returns invitation metadata for a token so the accept page can pre-fill info."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return api_err("token is required")
    hint = token[:8]
    candidate = query_one(
        "SELECT id,token_hash,role,ref_id,email,used FROM invitations WHERE token_hint=?",
        (hint,),
    )
    inv = None
    if candidate:
        try:
            if bcrypt.checkpw(token.encode(), candidate["token_hash"].encode()):
                inv = candidate
        except Exception:
            pass
    if not inv:
        return api_err("Invitation not found", 404)
    if inv["used"]:
        return api_err("This invitation has already been used", 410)
    # Resolve entity name
    entity_name = ""
    if inv["role"] == "school_admin" and inv["ref_id"]:
        school = query_one("SELECT name FROM schools WHERE id=?", (inv["ref_id"],))
        entity_name = school["name"] if school else ""
    elif inv["role"] == "ngo_officer" and inv["ref_id"]:
        ngo = query_one("SELECT org_name FROM ngos WHERE id=?", (inv["ref_id"],))
        entity_name = ngo["org_name"] if ngo else ""
    elif inv["role"] == "org_publisher" and inv["ref_id"]:
        org = query_one("SELECT name FROM organizations WHERE id=?", (inv["ref_id"],))
        entity_name = org["name"] if org else ""
    return jsonify({"role": inv["role"], "email": inv["email"], "entity_name": entity_name})


# Admin: add school

@app.route("/api/schools", methods=["POST"])
@require_role("admin", "school_admin")
def api_school_create():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    name    = (data.get("name") or "").strip()[:150]
    state   = (data.get("state") or "").strip()[:80]
    county  = (data.get("county") or "").strip()[:80]
    level   = (data.get("level") or "").strip()
    if not all([name, state, county, level]):
        return api_err("name, state, county, and level are required")
    if level not in {"primary", "secondary", "tertiary", "both"}:
        return api_err("level must be primary, secondary, tertiary, or both")

    # A school_admin self-listing their own institution goes into the same
    # moderation queue as materials/announcements/scholarships (approved=0,
    # reviewed via /api/admin/queue + /api/admin/approve) and is
    # auto-assigned to the creator so they can start completing the profile
    # immediately, without waiting on an admin to onboard them by invite.
    # A platform admin creating a school directly is still auto-approved.
    is_self_service = u["role"] == "school_admin"
    if is_self_service and u.get("school_id"):
        return api_err("Your account is already linked to a school")
    approved = 0 if is_self_service else 1

    sid = execute(
        """INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,
           email,capacity,status,enrollment,language,boarding,ownership,hours,description,
           registration_number,year_established,logo_url,address,mission,vision,core_values,
           subjects_offered,age_requirements,entry_grades,fees_structure,how_to_apply,
           headteacher_name,teaching_staff_count,classroom_count,
           has_library,has_laboratory,has_sports_facilities,has_water_sanitation,has_electricity,
           has_sports_clubs,has_arts_culture,has_academic_clubs,has_student_government,approved)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?,?,?, ?,?,?,?,?)""",
        (
            name, state, county, level,
            (data.get("type") or "mixed").strip(),
            (data.get("curriculum") or "National").strip(),
            (data.get("contact_name") or "").strip()[:100],
            (data.get("phone") or "").strip()[:30],
            (data.get("email") or "").strip()[:120] or None,
            data.get("capacity") or None,
            (data.get("status") or "open").strip(),
            data.get("enrollment") or 0,
            (data.get("language") or "English").strip(),
            (data.get("boarding") or "Day").strip(),
            (data.get("ownership") or "public").strip(),
            (data.get("hours") or "").strip()[:80] or None,
            (data.get("description") or "").strip() or None,
            (data.get("registration_number") or "").strip()[:80] or None,
            data.get("year_established") or None,
            (data.get("logo_url") or "").strip()[:300] or None,
            (data.get("address") or "").strip()[:300] or None,
            (data.get("mission") or "").strip() or None,
            (data.get("vision") or "").strip() or None,
            (data.get("core_values") or "").strip() or None,
            (data.get("subjects_offered") or "").strip() or None,
            (data.get("age_requirements") or "").strip()[:200] or None,
            (data.get("entry_grades") or "").strip()[:200] or None,
            (data.get("fees_structure") or "").strip() or None,
            (data.get("how_to_apply") or "").strip() or None,
            (data.get("headteacher_name") or "").strip()[:150] or None,
            data.get("teaching_staff_count") or None,
            data.get("classroom_count") or None,
            1 if data.get("has_library") else 0,
            1 if data.get("has_laboratory") else 0,
            1 if data.get("has_sports_facilities") else 0,
            1 if data.get("has_water_sanitation") else 0,
            1 if data.get("has_electricity") else 0,
            1 if data.get("has_sports_clubs") else 0,
            1 if data.get("has_arts_culture") else 0,
            1 if data.get("has_academic_clubs") else 0,
            1 if data.get("has_student_government") else 0,
            approved,
        ),
    )
    if is_self_service:
        execute("UPDATE users SET school_id=? WHERE id=?", (sid, u["id"]))
    log_audit(u["id"], "create_school", "school", sid)
    message = "School submitted for admin review" if is_self_service else "School created"
    return jsonify({"message": message, "id": sid, "invite_link": None, "approved": approved}), 201

# Admin: delete school

@app.route("/api/schools/<int:school_id>", methods=["DELETE"])
@require_role("admin")
def api_school_delete(school_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    school = query_one("SELECT id FROM schools WHERE id=?", (school_id,))
    if not school:
        return api_err("School not found", 404)
    execute("DELETE FROM admission_requirements WHERE school_id=?", (school_id,))
    execute("DELETE FROM school_exam_results WHERE school_id=?", (school_id,))
    execute("DELETE FROM schools WHERE id=?", (school_id,))
    # Otherwise the school_admin who owned it keeps a school_id pointing at
    # nothing: self-listing a new school is blocked (their account "already
    # has a school"), and their dashboard 404s since /api/my-school can't
    # find the row — Delete would silently leave them stuck either way.
    execute("UPDATE users SET school_id=NULL WHERE school_id=?", (school_id,))
    log_audit(u["id"], "delete_school", "school", school_id)
    return jsonify({"message": "School deleted"})

# Admin: delete user

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@require_role("admin")
def api_admin_delete_user(user_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    if user_id == u["id"]:
        return api_err("Cannot delete your own account")
    # applications and password_resets reference users without ON DELETE
    # CASCADE — deleting a user who ever applied to a scholarship or had a
    # password reset (self-service or admin-initiated) would otherwise fail
    # with a foreign-key constraint violation. bookmarks/notifications have
    # no FK constraint but are cleared too so no orphaned rows remain.
    execute("DELETE FROM applications WHERE user_id=?", (user_id,))
    execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
    execute("DELETE FROM bookmarks WHERE user_id=?", (user_id,))
    execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    execute("DELETE FROM users WHERE id=?", (user_id,))
    log_audit(u["id"], "delete_user", "user", user_id)
    return jsonify({"message": "User deleted"})

# School admin: own school dashboard

@app.route("/api/my-school")
@require_role("school_admin")
def api_my_school():
    u = request.current_user  # type: ignore[attr-defined]
    if not u.get("school_id"):
        return api_err("No school assigned to your account. Ask the platform admin to assign you.", 404)
    school = query_one("SELECT * FROM schools WHERE id=?", (u["school_id"],))
    if not school:
        return api_err("School not found", 404)
    reqs = query_all(
        "SELECT id,item_label,is_required,notes FROM admission_requirements WHERE school_id=? ORDER BY id",
        (u["school_id"],),
    )
    materials = query_all(
        "SELECT id,title,subject,grade,`year`,type,file_size,approved,rejection_reason,created_at "
        "FROM materials WHERE uploaded_by=? ORDER BY created_at DESC",
        (u["email"] or u["phone"],),
    )
    announcements = query_all(
        "SELECT id,title,body,audience,priority,expires_at,attachment_url,rejection_reason,"
        "approved,created_at FROM announcements "
        "WHERE source_id=? AND source_type='School' ORDER BY created_at DESC",
        (u["id"],),
    )
    bookmark_count = count(
        "SELECT COUNT(*) AS count FROM bookmarks WHERE item_type='school' AND item_id=?",
        (u["school_id"],),
    )
    exam_results = query_all(
        "SELECT id,year,subject,pass_rate FROM school_exam_results WHERE school_id=? ORDER BY year DESC,subject",
        (u["school_id"],),
    )
    return jsonify({
        "school": school,
        "requirements": reqs,
        "materials": materials,
        "announcements": announcements,
        "bookmark_count": bookmark_count,
        "exam_results": exam_results,
    })


# Org publisher: own organisation dashboard

@app.route("/api/my-org")
@require_role("org_publisher")
def api_my_org():
    u = request.current_user  # type: ignore[attr-defined]
    inv = query_one(
        "SELECT ref_id FROM invitations WHERE email=? AND role='org_publisher' AND used=1 ORDER BY id DESC LIMIT 1",
        (u.get("email") or "",),
    )
    org = None
    announcements: list = []
    if inv and inv["ref_id"]:
        org = query_one("SELECT * FROM organizations WHERE id=?", (inv["ref_id"],))
        if org:
            # Scoped by source_id (the posting user), not org_id — org_id is
            # a polymorphic reference (schools.id / ngos.id / organizations.id
            # all share the same column with no type discriminator in this
            # query), so filtering by it alone could leak another entity's
            # announcement if its id happened to match this org's id.
            announcements = query_all(
                "SELECT id,title,body,audience,priority,state,expires_at,attachment_url,"
                "rejection_reason,approved,created_at "
                "FROM announcements WHERE source_id=? ORDER BY created_at DESC",
                (u["id"],),
            )
    return jsonify({"org": org, "announcements": announcements})

# NGO officer: own organisation dashboard

@app.route("/api/my-ngo")
@require_role("ngo_officer")
def api_my_ngo():
    u = request.current_user  # type: ignore[attr-defined]
    my_ngo_id = _current_ngo_id(u)
    ngo = query_one("SELECT * FROM ngos WHERE id=?", (my_ngo_id,)) if my_ngo_id else None
    scholarships: list = []
    announcements: list = []
    programs: list = []
    app_count = 0
    if ngo:
        scholarships = query_all(
            "SELECT id,title,description,eligibility,deadline,how_to_apply,required_docs,"
            "external_link,approved,rejection_reason,"
            "slots_available,whats_covered,contact_person,poster_image_url,video_path,created_at "
            "FROM scholarships WHERE ngo_id=? ORDER BY created_at DESC",
            (ngo["id"],),
        )
        announcements = query_all(
            "SELECT id,title,body,audience,priority,expires_at,attachment_url,rejection_reason,"
            "approved,created_at FROM announcements "
            "WHERE source_id=? AND source_type='NGO' ORDER BY created_at DESC",
            (u["id"],),
        )
        programs = query_all(
            "SELECT id,name,target_beneficiaries,geographic_coverage,beneficiaries_per_year "
            "FROM ngo_programs WHERE ngo_id=? ORDER BY id DESC",
            (ngo["id"],),
        )
        app_count = count(
            "SELECT COUNT(*) AS count FROM applications a "
            "JOIN scholarships s ON s.id=a.scholarship_id WHERE s.ngo_id=?",
            (ngo["id"],),
        )
    return jsonify({
        "ngo": ngo,
        "scholarships": scholarships,
        "announcements": announcements,
        "programs": programs,
        "application_count": app_count,
    })


@app.route("/api/my-ngo", methods=["PUT"])
@require_role("ngo_officer")
def api_my_ngo_update():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    my_ngo_id = _current_ngo_id(u)
    ngo  = query_one("SELECT * FROM ngos WHERE id=?", (my_ngo_id,)) if my_ngo_id else None
    if not ngo:
        new_id = execute(
            """INSERT INTO ngos (org_name,contact,email,phone,description,verified,
               registration_number,year_founded,logo_url,org_type,areas_of_focus,
               state,county,website,mission,vision,core_values)
               VALUES (?,?,?,?,?,0, ?,?,?,?,?, ?,?,?,?,?,?)""",
            (
                (data.get("org_name") or "New Organisation").strip(),
                u["name"],
                u.get("email") or "",
                u.get("phone") or "",
                (data.get("description") or "").strip(),
                (data.get("registration_number") or "").strip()[:80] or None,
                data.get("year_founded") or None,
                (data.get("logo_url") or "").strip()[:300] or None,
                (data.get("org_type") or "").strip()[:80] or None,
                (data.get("areas_of_focus") or "").strip() or None,
                (data.get("state") or "").strip()[:80] or None,
                (data.get("county") or "").strip()[:80] or None,
                (data.get("website") or "").strip()[:300] or None,
                (data.get("mission") or "").strip() or None,
                (data.get("vision") or "").strip() or None,
                (data.get("core_values") or "").strip() or None,
            ),
        )
        execute("UPDATE users SET ngo_id=? WHERE id=?", (new_id, u["id"]))
    else:
        allowed = ["org_name", "contact", "email", "phone", "description",
                   "registration_number", "year_founded", "logo_url", "org_type",
                   "areas_of_focus", "state", "county", "website",
                   "mission", "vision", "core_values"]
        sets, params = _build_update_clause(data, allowed)
        if sets:
            params.append(ngo["id"])
            execute(f"UPDATE ngos SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Organisation profile updated"})


@app.route("/api/my-ngo/programs")
@require_role("ngo_officer")
def api_my_ngo_programs():
    u = request.current_user  # type: ignore[attr-defined]
    ngo_id = _current_ngo_id(u)
    if not ngo_id:
        return jsonify({"items": []})
    items = query_all(
        "SELECT id,name,target_beneficiaries,geographic_coverage,beneficiaries_per_year "
        "FROM ngo_programs WHERE ngo_id=? ORDER BY id DESC",
        (ngo_id,),
    )
    return jsonify({"items": items})


@app.route("/api/my-ngo/programs", methods=["POST"])
@require_role("ngo_officer")
def api_my_ngo_programs_create():
    u = request.current_user  # type: ignore[attr-defined]
    ngo_id = _current_ngo_id(u)
    if not ngo_id:
        return api_err("Save your organisation profile before adding programs", 400)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return api_err("Program name is required")
    pid = execute(
        "INSERT INTO ngo_programs (ngo_id,name,target_beneficiaries,geographic_coverage,beneficiaries_per_year) "
        "VALUES (?,?,?,?,?)",
        (
            ngo_id, name[:200],
            (data.get("target_beneficiaries") or "").strip()[:300] or None,
            (data.get("geographic_coverage") or "").strip()[:300] or None,
            data.get("beneficiaries_per_year") or None,
        ),
    )
    return jsonify({"message": "Program added", "id": pid}), 201


@app.route("/api/my-ngo/programs/<int:program_id>", methods=["DELETE"])
@require_role("ngo_officer")
def api_my_ngo_programs_delete(program_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    ngo_id = _current_ngo_id(u)
    if not ngo_id:
        return api_err("Program not found", 404)
    execute("DELETE FROM ngo_programs WHERE id=? AND ngo_id=?", (program_id, ngo_id))
    return jsonify({"message": "Program removed"})


@app.route("/api/ngos/<int:ngo_id>/programs")
def api_ngo_programs_public(ngo_id: int):
    items = query_all(
        "SELECT id,name,target_beneficiaries,geographic_coverage,beneficiaries_per_year "
        "FROM ngo_programs WHERE ngo_id=? ORDER BY id",
        (ngo_id,),
    )
    return jsonify({"items": items})


@app.route("/healthz")
def healthz():
    try:
        from sqlalchemy import text
        with get_db() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": {"engine": db_engine.dialect.name, "connected": True}})
    except Exception as exc:
        log.error("Health check DB error: %s", exc)
        return jsonify({"status": "degraded", "database": {"engine": db_engine.dialect.name, "connected": False}}), 503


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return api_err("Not found", 404)
    return redirect(url_for("home"))


@app.errorhandler(413)
def too_large(_):
    return api_err("File too large", 413)


@app.errorhandler(500)
def internal_error(exc):
    log.exception("Unhandled exception: %s", exc)
    if request.path.startswith("/api/"):
        return api_err("An unexpected error occurred", 500)
    return redirect(url_for("home"))

if __name__ == "__main__":
    init_db()
    # Debug/reloader is opt-in via FLASK_DEBUG — never on by default, since
    # Werkzeug's debug console allows arbitrary code execution if this ever
    # ends up reachable outside local development.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    # Skip the Werkzeug reloader's parent monitor process — it never serves
    # requests, so starting the scheduler there would just double the jobs.
    # Must check the env var directly rather than app.debug: app.debug isn't
    # set to match debug_mode until app.run() below, so it read as False
    # here even in debug mode, which made this condition always true and
    # started the scheduler in the parent monitor process too.
    if not debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        import scheduler as background_jobs
        background_jobs.start(app)
    # threaded=True — the SSE stream in /api/notifications/stream holds its
    # connection open, and the dev server is single-threaded by default.
    app.run(debug=debug_mode, port=int(os.environ.get("PORT", 5000)), threaded=True)
