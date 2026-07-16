from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import bcrypt
import jwt
from flask import Flask, jsonify, render_template, request, redirect, url_for, send_file as flask_send_file, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename

try:
    import mysql.connector as mysql_connector
except Exception:  # pragma: no cover - optional dependency for local SQLite runs
    mysql_connector = None

BASE_DIR          = Path(__file__).resolve().parent.parent
FRONTEND_DIR      = BASE_DIR / "frontend"
HTML_DIR          = FRONTEND_DIR / "html"
CSS_DIR           = FRONTEND_DIR / "css"
JS_DIR            = FRONTEND_DIR / "javascript"
ASSETS_DIR        = FRONTEND_DIR / "assets"
DB_DIR            = BASE_DIR / "database"
DB_PATH           = DB_DIR / "eduportal.sqlite3"
MYSQL_HOST        = os.environ.get("MYSQL_HOST", "").strip()
MYSQL_PORT        = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER        = os.environ.get("MYSQL_USER", "").strip()
MYSQL_PASSWORD    = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE    = os.environ.get("MYSQL_DATABASE", "").strip()
JWT_SECRET        = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-in-prod")
UPLOAD_FOLDER     = ASSETS_DIR / "avatars"
MATERIALS_FOLDER  = ASSETS_DIR / "materials"
ALLOWED_EXTENSIONS      = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_MATERIAL_EXTS   = {"pdf"}
MAX_AVATAR_BYTES         = 2 * 1024 * 1024   # 2 MB
MAX_MATERIAL_BYTES       = 20 * 1024 * 1024  # 20 MB
_DB_READY = False


def _mysql_enabled() -> bool:
    return bool(MYSQL_HOST and MYSQL_DATABASE and mysql_connector is not None)


def _adapt_sql(sql: str) -> str:
    if not _mysql_enabled():
        return sql
    sql = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    sql = sql.replace("INSERT OR REPLACE INTO", "REPLACE INTO")
    sql = sql.replace("?", "%s")
    return sql


def _adapt_schema(sql: str) -> str:
    if not _mysql_enabled():
        return sql
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INT NOT NULL AUTO_INCREMENT PRIMARY KEY")
    sql = sql.replace("TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    return sql


class DBProxy:
    def __init__(self, conn):
        self._conn = conn
        if not _mysql_enabled():
            self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: tuple = ()):
        sql = _adapt_sql(sql)
        if _mysql_enabled():
            cur = self._conn.cursor(dictionary=True)
            cur.execute(sql, params)
            return cur
        return self._conn.execute(sql, params)

    def executescript(self, script: str):
        if _mysql_enabled():
            for statement in _adapt_schema(script).split(";"):
                stmt = statement.strip()
                if stmt:
                    self.execute(stmt)
            return None
        return self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

app = Flask(
    __name__,
    template_folder=str(HTML_DIR),
    static_folder=None,
)
app.config["MAX_CONTENT_LENGTH"] = MAX_MATERIAL_BYTES
DB_DIR.mkdir(parents=True, exist_ok=True)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/static/<path:filename>")
def static_files(filename: str):
    # CSS compatibility
    if filename == "styles.css":
        return send_from_directory(str(CSS_DIR), "styles.css")
    if filename.startswith("pages/"):
        return send_from_directory(str(CSS_DIR / "pages"), filename[len("pages/"):])
    if filename.startswith("shared/"):
        return send_from_directory(str(CSS_DIR / "shared"), filename[len("shared/"):])
    if filename.startswith("layout/"):
        return send_from_directory(str(CSS_DIR / "layout"), filename[len("layout/"):])
    if filename.startswith("auth/"):
        return send_from_directory(str(CSS_DIR / "auth"), filename[len("auth/"):])
    if filename.startswith("html/"):
        return send_from_directory(str(CSS_DIR / "html"), filename[len("html/"):])
    # Backward compatibility for previous modular imports under /static/css/**
    if filename.startswith("css/layout/"):
        return send_from_directory(str(CSS_DIR / "layout"), filename[len("css/layout/"):])
    if filename.startswith("css/auth/"):
        return send_from_directory(str(CSS_DIR / "auth"), filename[len("css/auth/"):])

    # JavaScript compatibility
    if filename in {"app.js", "sidebar.js"}:
        return send_from_directory(str(JS_DIR), filename)
    if filename.startswith("app/"):
        return send_from_directory(str(JS_DIR / "app"), filename[len("app/"):])
    if filename.startswith("navigation/"):
        return send_from_directory(str(JS_DIR / "navigation"), filename[len("navigation/"):])
    # Backward compatibility for previous modular imports under /static/js/**
    if filename.startswith("js/app/"):
        return send_from_directory(str(JS_DIR / "app"), filename[len("js/app/"):])
    if filename.startswith("js/navigation/"):
        return send_from_directory(str(JS_DIR / "navigation"), filename[len("js/navigation/"):])

    # Uploaded and generated assets
    if filename.startswith("avatars/"):
        return send_from_directory(str(ASSETS_DIR / "avatars"), filename[len("avatars/"):])
    if filename.startswith("materials/"):
        return send_from_directory(str(ASSETS_DIR / "materials"), filename[len("materials/"):])

    return jsonify({"error": "Not found"}), 404

# ── DB helpers ────────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    if _mysql_enabled():
        conn = mysql_connector.connect(  # type: ignore[union-attr]
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=False,
        )
    else:
        conn = sqlite3.connect(DB_PATH)
    proxy = DBProxy(conn)
    try:
        yield proxy
        proxy.commit()
    except Exception:
        proxy.rollback()
        raise
    finally:
        proxy.close()


def _table_columns(db, table: str) -> set[str]:
    if _mysql_enabled():
        cur = db.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?",
            (MYSQL_DATABASE, table),
        )
        return {row["COLUMN_NAME"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}

def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]

def query_one(sql: str, params: tuple = ()) -> dict | None:
    with get_db() as db:
        row = db.execute(sql, params).fetchone()
    return dict(row) if row else None

def execute(sql: str, params: tuple = ()) -> int:
    with get_db() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid or 0

def count(sql: str, params: tuple = ()) -> int:
    r = query_one(sql, params)
    return r["count"] if r else 0


def init_db() -> None:
    with get_db() as db:
        # Schema migration: add file_path to materials if missing
        mcols = list(_table_columns(db, "materials"))
        if "file_path" not in mcols and mcols:  # table exists
            try:
                db.execute("ALTER TABLE materials ADD COLUMN file_path TEXT")
            except Exception:
                pass
        schema = _adapt_schema("""
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
                notes TEXT,
                FOREIGN KEY (school_id) REFERENCES schools(id)
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ngo_id) REFERENCES ngos(id)
            );
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scholarship_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'submitted',
                note TEXT,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, scholarship_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (scholarship_id) REFERENCES scholarships(id)
            );
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_type, item_id)
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
        """)
        db.executescript(schema)
        scholarship_columns = _table_columns(db, "scholarships")
        if "required_docs" not in scholarship_columns:
            db.execute("ALTER TABLE scholarships ADD COLUMN required_docs TEXT")
        if "external_link" not in scholarship_columns:
            db.execute("ALTER TABLE scholarships ADD COLUMN external_link TEXT")
        ngo_columns = _table_columns(db, "ngos")
        if "description" not in ngo_columns:
            db.execute("ALTER TABLE ngos ADD COLUMN description TEXT")
        # Safe migrations — add columns that may not exist in older DBs
        _migrate(db)
        db.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                user_id INTEGER PRIMARY KEY,
                token TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Indexes for performance
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_users_email   ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_phone   ON users(phone);
            CREATE INDEX IF NOT EXISTS idx_schools_state ON schools(state);
            CREATE INDEX IF NOT EXISTS idx_apps_user     ON applications(user_id);
            CREATE INDEX IF NOT EXISTS idx_apps_sch      ON applications(scholarship_id);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id);
            CREATE INDEX IF NOT EXISTS idx_materials_approved ON materials(approved);
            CREATE INDEX IF NOT EXISTS idx_scholarships_approved ON scholarships(approved);
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                ref_id INTEGER,
                email TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        school_count = db.execute("SELECT COUNT(*) AS count FROM schools").fetchone()
        school_count_val = school_count["count"] if isinstance(school_count, dict) else school_count[0]
        if school_count_val == 0:
            _seed(db)
        db.commit()


def _migrate(db) -> None:
    migrations = [
        "ALTER TABLE scholarships ADD COLUMN required_docs TEXT DEFAULT ''",
        "ALTER TABLE scholarships ADD COLUMN external_link TEXT DEFAULT ''",
        "ALTER TABLE ngos ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN notify_email INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_sms INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_inapp INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN grade TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN school_name TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN child_school TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN child_grade TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN subjects TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN institution TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN experience_years INTEGER DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN managed_school TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN position TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN school_id INTEGER DEFAULT NULL",
        "ALTER TABLE schools ADD COLUMN type TEXT NOT NULL DEFAULT 'mixed'",
        """CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scholarship_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            note TEXT,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, scholarship_id)
        )""",
    ]
    for sql in migrations:
        try:
            db.execute(sql)
        except Exception:
            pass


def _seed(db) -> None:
    pw = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt()).decode()
    db.execute(
        "INSERT OR IGNORE INTO users (name,email,phone,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,?,1)",
        ("Platform Admin", "admin@eduportal.ss", "+211000000000", pw, "admin", "Central Equatoria", "Juba"),
    )
    schools = [
        ("Juba Day Secondary School","Central Equatoria","Juba","secondary","mixed","National","Amina Mayen","+211 912 000 101","juba.day@example.com",1200,"open",980,"English","Day","7:30 AM – 3:30 PM","A long-running public secondary school serving central Juba."),
        ("Bor Primary School","Jonglei","Bor South","primary","mixed","National","Peter Aken","+211 912 000 102","bor.primary@example.com",800,"open",640,"English","Day","7:00 AM – 1:00 PM","A community school with broad catchment across Bor South."),
        ("Wau Girls Secondary School","Western Bahr el Ghazal","Wau","secondary","girls","National","Grace Mahad","+211 912 000 103","wau.girls@example.com",900,"open",725,"English","Boarding","8:00 AM – 4:00 PM","Girls-focused secondary school with boarding support."),
        ("Rumbek Academy","Lakes","Rumbek East","secondary","mixed","National","Deng Atar","+211 912 000 104","rumbek.academy@example.com",1000,"open",810,"English","Day","7:30 AM – 3:30 PM","Mixed secondary school known for exam preparation."),
        ("Malakal Model School","Upper Nile","Malakal","primary","mixed","National","Hilda Acuil","+211 912 000 105","malakal.model@example.com",700,"limited",560,"English","Day","7:00 AM – 1:00 PM","A model primary school near the Nile corridor."),
        ("Yambio Community School","Western Equatoria","Yambio","primary","mixed","National","Martin Yel","+211 912 000 106","yambio.community@example.com",650,"open",520,"English","Day","7:00 AM – 1:00 PM","Community-rooted school with simple admission requirements."),
        ("Kuajok Technical School","Warrap","Kuajok","secondary","mixed","National","Rebecca Chuol","+211 912 000 107","kuajok.tech@example.com",950,"open",760,"English","Day","8:00 AM – 4:00 PM","Technical learning and practical sciences focus."),
        ("Aweil Girls Primary","Northern Bahr el Ghazal","Aweil East","primary","girls","National","Mayen Chol","+211 912 000 108","aweil.girls@example.com",600,"open",480,"English","Day","7:00 AM – 1:00 PM","Primary school with strong parent engagement."),
        ("Torit Preparatory School","Eastern Equatoria","Torit","secondary","mixed","National","James Lado","+211 912 000 109","torit.prep@example.com",850,"open",690,"English","Day","7:30 AM – 3:00 PM","Prepares learners for national examinations."),
        ("Bentiu Bridge School","Unity","Bentiu","primary","mixed","National","Martha Kueth","+211 912 000 110","bentiu.bridge@example.com",500,"open",410,"English","Day","7:00 AM – 1:00 PM","Stable access point for learning in Unity state."),
    ]
    school_ids: list[int] = []
    for s in schools:
        cur = db.execute(
            "INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,email,capacity,status,enrollment,language,boarding,hours,description) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", s)
        school_ids.append(cur.lastrowid or 0)
    req_sets = [
        [("Birth certificate or baptism certificate",1,"Bring original plus one photocopy."),("Two passport photos",1,"Recent photos with plain background."),("Last report card",1,"Required for transfer applicants.")],
        [("Child health card",1,"Only for P1 intake."),("Copy of parent ID",1,"Any official identity document accepted.")],
        [("Completed admission form",1,None),("Transfer letter",0,"Needed only when moving from another school."),("Two passport photos",1,None)],
    ]
    for i, sid in enumerate(school_ids):
        for label, req, notes in req_sets[i % len(req_sets)]:
            db.execute("INSERT INTO admission_requirements (school_id,item_label,is_required,notes) VALUES (?,?,?,?)",(sid,label,req,notes))
    for title,subject,grade,year,mtype,size,preview in [
        ("Mathematics P8 Past Paper 2024","Mathematics","P8",2024,"past paper","1.8 MB","Arithmetic, geometry, and measurement questions."),
        ("English S4 Study Notes","English","S4",2023,"study guide","900 KB","Revision notes for comprehension and essay writing."),
        ("Science S6 Teacher Notes","Science","S6",2024,"teacher note","2.3 MB","Practical science revision notes for senior learners."),
        ("Social Studies P5 Past Paper","Social Studies","P5",2022,"past paper","1.1 MB","A lightweight practice paper for primary learners."),
    ]:
        db.execute("INSERT INTO materials (title,subject,grade,year,type,file_size,preview_text,uploaded_by,approved) VALUES (?,?,?,?,?,?,?,?,1)",
                   (title,subject,grade,year,mtype,size,preview,"admin@eduportal.ss"))
    for title,body,source,audience,expires in [
        ("2026 National Exam Registration","Registration for national exams is open across all states until 30 June.","Ministry","students","2026-06-30"),
        ("School Holiday Notice","All schools in Jonglei should observe the updated weather-related holiday schedule.","School","parents","2026-06-10"),
        ("Teacher Workshop in Juba","SSNEC will host a curriculum support workshop for teachers next week.","SSNEC","teachers","2026-05-28"),
    ]:
        db.execute("INSERT INTO announcements (title,body,source_type,audience,expires_at,approved) VALUES (?,?,?,?,?,1)",(title,body,source,audience,expires))
    ngo_ids: list[int] = []
    for org,contact,email,phone,desc in [
        ("Future South Sudan Trust","Grace Atong","contact@futuress.org","+211 912 200 111","Supporting secondary learners across South Sudan since 2018."),
        ("Girls in STEM Initiative","Luka Bullen","info@girlsinstem.ss","+211 912 200 112","Empowering girls to pursue science and technology careers."),
    ]:
        cur = db.execute("INSERT INTO ngos (org_name,contact,email,phone,description,verified) VALUES (?,?,?,?,?,1)",(org,contact,email,phone,desc))
        ngo_ids.append(cur.lastrowid or 0)
    for ngo_id,title,desc,elig,deadline,how,docs,link in [
        (ngo_ids[0],"Secondary School Support Grant","Partial tuition support for secondary learners with strong attendance.","Grade 9–12, South Sudan resident, not already funded","2026-07-20","Complete the online application and attach your latest report card.","Report card, birth certificate, recommendation letter","https://futuress.org/apply"),
        (ngo_ids[1],"Girls STEM Bursary","Supports girls entering science and technology pathways.","Female learners in S4–S6, any state","2026-08-15","Submit the bursary form and a short motivation letter.","Motivation letter, school ID, report card","https://girlsinstem.ss/bursary"),
        (ngo_ids[0],"Rural Materials Pack","Book and stationery support for learners in remote counties.","Primary learners in rural counties","2026-06-25","Contact your school admin for the referral form.","Referral form from school admin",None),
    ]:
        db.execute("INSERT INTO scholarships (ngo_id,title,description,eligibility,deadline,how_to_apply,required_docs,external_link,approved) VALUES (?,?,?,?,?,?,?,?,1)",
                   (ngo_id,title,desc,elig,deadline,how,docs,link))


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _make_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def _get_current_user() -> dict | None:
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
        user = _get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        request.current_user = user  # type: ignore[attr-defined]
        return fn(*args, **kwargs)
    return wrapper

def require_role(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _get_current_user()
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
    execute("INSERT INTO audit_log (admin_id,action,target_type,target_id,note) VALUES (?,?,?,?,?)",
            (admin_id, action, target_type, target_id, note))

@app.before_request
def ensure_db():
    global _DB_READY
    if not _DB_READY:
        init_db()
        _DB_READY = True


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

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

@app.route("/schools/<int:school_id>")
def school_profile(school_id: int):
    return render_template("school.html", school_id=school_id)

# ── Auth API ──────────────────────────────────────────────────────────────────

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
    if int(user.get("verified", 0)) < 1:
        return api_err("This account is deactivated", 403)
    try:
        valid = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    except Exception:
        valid = False
    if not valid:
        return api_err("Invalid credentials", 401)
    return jsonify({"token": _make_token(user), "user": {"id": user["id"], "name": user["name"], "role": user["role"], "state": user["state"]}})

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
    if role not in {"student","parent","teacher","school_admin","ngo_officer"}:
        return api_err("Invalid role")
    if query_one("SELECT id FROM users WHERE email=? OR phone=?", (email, phone)):
        return api_err("An account with those details already exists", 409)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    uid = execute(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,?,1)",
        (name, email, phone, pw_hash, role, state, county),
    )
    user = query_one("SELECT * FROM users WHERE id=?", (uid,))
    return jsonify({"token": _make_token(user), "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}), 201

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
    }})

@app.route("/api/me/avatar", methods=["POST"])
@require_auth
def api_me_avatar():
    u = request.current_user  # type: ignore[attr-defined]
    if "avatar" not in request.files:
        return api_err("No file uploaded")
    file = request.files["avatar"]
    if not file.filename:
        return api_err("Empty filename")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return api_err("Only JPG, PNG, GIF, or WEBP files are allowed")
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    filename = f"user_{u['id']}.{ext}"
    file.save(str(UPLOAD_FOLDER / filename))
    avatar_url = f"/static/avatars/{filename}"
    execute("UPDATE users SET avatar=? WHERE id=?", (avatar_url, u["id"]))
    return jsonify({"avatar": avatar_url})

@app.route("/api/me", methods=["PUT"])
@require_auth
def api_me_update():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    allowed = ["name","email","phone","state","county",
               "notify_email","notify_sms","notify_inapp",
               "grade","school_name","child_school","child_grade",
               "subjects","institution","experience_years","managed_school","position"]
    sets, params = [], []
    for field in allowed:
        if field in data:
            sets.append(f"{field}=?")
            params.append(data[field])
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
    return jsonify({"message": "Password changed"})

@app.route("/api/deactivate-account", methods=["POST"])
@require_auth
def api_deactivate_account():
    u = request.current_user  # type: ignore[attr-defined]
    execute("UPDATE users SET verified=-1 WHERE id=?", (u["id"],))
    return jsonify({"message": "Account deactivated"})


# ── Stats ─────────────────────────────────────────────────────────────────────

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

# ── Schools ───────────────────────────────────────────────────────────────────

@app.route("/api/schools")
def api_schools():
    state   = request.args.get("state","").strip()
    level   = request.args.get("level","").strip()
    type_   = request.args.get("type","").strip()
    boarding = request.args.get("boarding","").strip()
    search  = request.args.get("search","").strip()
    page    = max(1, int(request.args.get("page","1") or 1))
    per_page = 6
    sql = "SELECT id,name,state,county,level,type,status,enrollment,boarding,description FROM schools WHERE 1=1"
    params: list = []
    if state:    sql += " AND state=?";    params.append(state)
    if level:    sql += " AND level=?";    params.append(level)
    if type_:    sql += " AND type=?";     params.append(type_)
    if boarding: sql += " AND boarding=?"; params.append(boarding)
    if search:
        sql += " AND (name LIKE ? OR county LIKE ? OR state LIKE ?)"
        t = f"%{search}%"; params.extend([t,t,t])
    total = count(f"SELECT COUNT(*) AS count FROM ({sql})", tuple(params))  # noqa: S608
    sql += f" ORDER BY name LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return jsonify({"items": query_all(sql, tuple(params)), "total": total, "page": page, "per_page": per_page})

@app.route("/api/schools/<int:school_id>")
def api_school_detail(school_id: int):
    school = query_one("SELECT * FROM schools WHERE id=?", (school_id,))
    if not school:
        return api_err("School not found", 404)
    return jsonify({"school": school})

@app.route("/api/schools/<int:school_id>", methods=["PUT"])
@require_auth
def api_school_update(school_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    # Only the assigned school_admin or a platform admin may update
    if u["role"] != "admin" and not (u["role"] == "school_admin" and u["school_id"] == school_id):
        return api_err("You are not authorised to edit this school", 403)
    data = request.get_json(silent=True) or {}
    allowed = ["name","state","county","level","type","curriculum","contact_name",
               "phone","email","capacity","status","enrollment","language","boarding",
               "hours","description"]
    sets, params = [], []
    for field in allowed:
        if field in data:
            sets.append(f"{field}=?")
            params.append(data[field])
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
    if u["role"] != "admin" and not (u["role"] == "school_admin" and u["school_id"] == school_id):
        return api_err("You are not authorised to edit this school", 403)
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

# ── Materials ─────────────────────────────────────────────────────────────────

@app.route("/api/materials")
def api_materials():
    subject  = request.args.get("subject","").strip()
    grade    = request.args.get("grade","").strip()
    year     = request.args.get("year","").strip()
    doc_type = request.args.get("type","").strip()
    search   = request.args.get("search","").strip()
    approved = request.args.get("approved","1").strip()
    page     = max(1, int(request.args.get("page","1") or 1))
    per_page = 12
    approved_val = 0 if approved == "0" else 1
    sql = "SELECT id,title,subject,grade,year,type,file_size,preview_text,created_at FROM materials WHERE approved=?"
    params: list = [approved_val]
    if subject:  sql += " AND subject=?";  params.append(subject)
    if grade:    sql += " AND grade=?";    params.append(grade)
    if year:     sql += " AND year=?";     params.append(int(year))
    if doc_type: sql += " AND type=?";     params.append(doc_type)
    if search:
        sql += " AND (title LIKE ? OR subject LIKE ?)"
        t = f"%{search}%"; params.extend([t,t])
    total = count(f"SELECT COUNT(*) AS count FROM ({sql})", tuple(params))  # noqa: S608
    sql += f" ORDER BY year DESC, title ASC LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return jsonify({"items": query_all(sql, tuple(params)), "total": total, "page": page, "per_page": per_page})

@app.route("/api/materials/<int:material_id>")
def api_material_detail(material_id: int):
    row = query_one("SELECT id,title,subject,grade,year,type,file_size,preview_text,created_at FROM materials WHERE id=? AND approved=1", (material_id,))
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
    mid = execute(
        "INSERT INTO materials (title,subject,grade,year,type,uploaded_by,approved) VALUES (?,?,?,?,?,?,0)",
        (title, subject, grade, int(year), doc_type, u["email"] or u["phone"]),
    )
    return jsonify({"message": "Material submitted for review", "id": mid}), 201


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
        return api_err("Only PDF files are allowed")
    MATERIALS_FOLDER.mkdir(parents=True, exist_ok=True)
    safe_name = f"material_{material_id}_{secure_filename(f.filename)}"
    save_path = MATERIALS_FOLDER / safe_name
    f.save(str(save_path))
    file_size = f"{save_path.stat().st_size // 1024} KB"
    execute("UPDATE materials SET file_path=?, file_size=? WHERE id=?",
            (f"/static/materials/{safe_name}", file_size, material_id))
    return jsonify({"message": "File uploaded", "file_path": f"/static/materials/{safe_name}"})


@app.route("/api/materials/<int:material_id>/download")
@require_auth
def api_material_download(material_id: int):
    """Serve a material PDF for authenticated users."""
    mat = query_one("SELECT * FROM materials WHERE id=? AND approved=1", (material_id,))
    if not mat:
        return api_err("Material not found", 404)
    file_path_rel = mat.get("file_path")
    if not file_path_rel:
        return api_err("No file has been uploaded for this material yet", 404)
    clean_rel = file_path_rel.replace("/static/", "", 1).lstrip("/")
    disk_path = ASSETS_DIR / clean_rel
    if not disk_path.exists():
        return api_err("File not found on server", 404)
    return flask_send_file(
        str(disk_path),
        as_attachment=True,
        download_name=disk_path.name,
        mimetype="application/pdf",
    )

# ── Announcements ─────────────────────────────────────────────────────────────

@app.route("/api/announcements")
def api_announcements():
    source     = request.args.get("source","").strip()
    audience   = request.args.get("audience","").strip()
    date_from  = request.args.get("date_from","").strip()
    date_to    = request.args.get("date_to","").strip()
    search     = request.args.get("search","").strip()
    approved   = request.args.get("approved","1").strip()
    approved_val = 0 if approved == "0" else 1
    sql = "SELECT id,title,body,source_type,audience,expires_at,created_at FROM announcements WHERE approved=?"
    params: list = [approved_val]
    if source:    sql += " AND source_type=?";                  params.append(source)
    if audience:  sql += " AND audience=?";                     params.append(audience)
    if date_from: sql += " AND date(created_at) >= date(?)";    params.append(date_from)
    if date_to:   sql += " AND date(created_at) <= date(?)";    params.append(date_to)
    if search:
        sql += " AND (title LIKE ? OR body LIKE ?)"
        t = f"%{search}%"; params.extend([t, t])
    sql += " ORDER BY created_at DESC"
    return jsonify({"items": query_all(sql, tuple(params))})

@app.route("/api/announcements", methods=["POST"])
@require_role("school_admin","ngo_officer")
def api_announcements_post():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    title      = (data.get("title") or "").strip()
    body       = (data.get("body") or "").strip()
    source_type = (data.get("source_type") or "School").strip()
    audience   = (data.get("audience") or "").strip()
    expires_at = (data.get("expires_at") or "").strip() or None
    if not all([title, body, audience]):
        return api_err("title, body, and audience are required")
    approved = 1 if u["role"] == "admin" else 0
    aid = execute(
        "INSERT INTO announcements (title,body,source_type,source_id,audience,expires_at,approved) VALUES (?,?,?,?,?,?,?)",
        (title, body, source_type, u["id"], audience, expires_at, approved),
    )
    return jsonify({"message": "Announcement submitted", "id": aid}), 201


# ── Scholarships ──────────────────────────────────────────────────────────────

@app.route("/api/scholarships")
def api_scholarships():
    deadline_after = request.args.get("deadline_after","").strip()
    search         = request.args.get("search","").strip()
    state          = request.args.get("state","").strip()
    eligibility    = request.args.get("eligibility","").strip()
    approved       = request.args.get("approved","1").strip()
    approved_val   = 0 if approved == "0" else 1
    sql = """SELECT s.id,s.title,s.description,s.eligibility,s.deadline,
                  s.how_to_apply,s.external_link,
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
    sql += " ORDER BY s.deadline ASC"
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
    # Auto-resolve ngo_id from the officer's email/phone — no manual ngo_id needed
    ngo = query_one(
        "SELECT id FROM ngos WHERE email=? OR phone=?",
        (u.get("email") or "", u.get("phone") or ""),
    )
    ngo_id = ngo["id"] if ngo else None
    sid = execute(
        "INSERT INTO scholarships (ngo_id,title,description,eligibility,deadline,how_to_apply,required_docs,external_link,approved) VALUES (?,?,?,?,?,?,?,?,0)",
        (ngo_id, title, desc, elig, deadline, how, docs, link),
    )
    return jsonify({"message": "Scholarship submitted for review", "id": sid}), 201

# ── Applications ──────────────────────────────────────────────────────────────

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
    # C — send email notification to applicant
    app_row = query_one(
        """SELECT a.*, u.email AS applicant_email, u.name AS applicant_name,
                  u.notify_email, s.title AS scholarship_title
           FROM applications a
           JOIN users u ON u.id=a.user_id
           JOIN scholarships s ON s.id=a.scholarship_id
           WHERE a.id=?""",
        (app_id,),
    )
    if app_row and app_row.get("applicant_email") and app_row.get("notify_email"):
        label = status.replace("_", " ").title()
        send_email(
            app_row["applicant_email"],
            f"EduPortal — Application Update: {app_row['scholarship_title']}",
            f"Dear {app_row['applicant_name']},\n\nYour application for \"{app_row['scholarship_title']}\" has been updated to: {label}.\n\nLog in to EduPortal South Sudan to view details.\n\nEduPortal South Sudan",
        )
    return jsonify({"message": f"Application status updated to {status}"})

# ── Bookmarks ─────────────────────────────────────────────────────────────────

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
    materials   = fetch_by_ids("materials",   "id,title,subject,grade,year,type,file_size,preview_text,file_path", material_ids)
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
    execute("INSERT OR IGNORE INTO bookmarks (user_id,item_type,item_id) VALUES (?,?,?)",
            (u["id"], item_type, item_id))
    return jsonify({"message": "Saved"})

@app.route("/api/bookmarks/<int:bookmark_id>", methods=["DELETE"])
@require_auth
def api_bookmark_delete(bookmark_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    execute("DELETE FROM bookmarks WHERE id=? AND user_id=?", (bookmark_id, u["id"]))
    return jsonify({"message": "Removed"})


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/api/admin/queue")
@require_role("admin")
def api_admin_queue():
    mat_items = query_all(
        "SELECT id,title,subject,grade,year,type FROM materials WHERE approved=0 ORDER BY created_at DESC")
    ann_items = query_all(
        "SELECT id,title,body,source_type,audience,expires_at FROM announcements WHERE approved=0 ORDER BY created_at DESC")
    sch_items = query_all(
        """SELECT s.id,s.title,s.description,s.deadline,n.org_name AS provider
           FROM scholarships s LEFT JOIN ngos n ON n.id=s.ngo_id
           WHERE s.approved=0 ORDER BY s.deadline ASC""")
    return jsonify({
        "materials":     len(mat_items),
        "announcements": len(ann_items),
        "scholarships":  len(sch_items),
        "material_items":     [{"id":r["id"],"title":r["title"],"meta":f"{r['subject']} · {r['grade']} · {r['year']} · {r['type']}"} for r in mat_items],
        "announcement_items": [{"id":r["id"],"title":r["title"],"meta":f"{r['source_type']} · {r['audience']} · expires {r['expires_at']}"} for r in ann_items],
        "scholarship_items":  [{"id":r["id"],"title":r["title"],"meta":f"{r['provider']} · deadline {r['deadline']}"} for r in sch_items],
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
    table_map   = {"material":"materials","announcement":"announcements","scholarship":"scholarships"}
    if target_type not in table_map or not target_id:
        return api_err("target_type and target_id required")
    val = 1 if action == "approve" else 0
    execute(f"UPDATE {table_map[target_type]} SET approved=? WHERE id=?", (val, int(target_id)))  # noqa: S608
    log_audit(u["id"], action, target_type, int(target_id), note)
    return jsonify({"message": f"{target_type} {action}d"})

@app.route("/api/admin/users")
@require_role("admin")
def api_admin_users():
    role = request.args.get("role","").strip()
    sql  = "SELECT id,name,email,phone,role,state,county,verified,created_at,school_id FROM users"
    params: list = []
    if role:
        sql += " WHERE role=?"; params.append(role)
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
    if status:
        sql += " AND a.status = ?"
        params.append(status)
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

@app.route("/api/admin/users/<int:user_id>/suspend", methods=["POST"])
@require_role("admin")
def api_admin_suspend(user_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    execute("UPDATE users SET verified=-1 WHERE id=?", (user_id,))
    log_audit(u["id"], "suspend", "user", user_id)
    return jsonify({"message": "User suspended"})

@app.route("/api/admin/users/<int:user_id>/role", methods=["POST"])
@require_role("admin")
def api_admin_change_role(user_id: int):
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip()
    valid_roles = {"student","parent","teacher","school_admin","ngo_officer","admin"}
    if new_role not in valid_roles:
        return api_err(f"role must be one of: {', '.join(valid_roles)}")
    execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
    log_audit(u["id"], f"change_role_to_{new_role}", "user", user_id)
    return jsonify({"message": f"Role changed to {new_role}"})

@app.route("/api/admin/audit-log")
@require_role("admin")
def api_audit_log():
    return jsonify({"items": query_all("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 200")})

@app.route("/api/admin/analytics")
@require_role("admin")
def api_admin_analytics():
    users_by_state = query_all(
        "SELECT COALESCE(state,'Unknown') AS state, COUNT(*) AS count FROM users GROUP BY COALESCE(state,'Unknown') ORDER BY count DESC")
    bookmarked_schools = query_all(
        """SELECT s.name,COUNT(*) AS count FROM bookmarks b
           JOIN schools s ON s.id=b.item_id WHERE b.item_type='school'
           GROUP BY s.id,s.name ORDER BY count DESC LIMIT 5""")
    top_materials = query_all(
        """SELECT m.title,m.subject,m.grade,COUNT(b.id) AS saves
           FROM materials m LEFT JOIN bookmarks b ON b.item_id=m.id AND b.item_type='material'
           WHERE m.approved=1 GROUP BY m.id ORDER BY saves DESC LIMIT 5""")
    app_counts = query_all(
        """SELECT s.title,COUNT(a.id) AS applications
           FROM scholarships s LEFT JOIN applications a ON a.scholarship_id=s.id
           WHERE s.approved=1 GROUP BY s.id ORDER BY applications DESC LIMIT 5""")
    return jsonify({
        "users_by_state":    users_by_state,
        "bookmarked_schools": bookmarked_schools,
        "top_materials":     top_materials,
        "scholarship_applications": app_counts,
        "approved": {
            "materials":     count("SELECT COUNT(*) AS count FROM materials WHERE approved=1"),
            "announcements": count("SELECT COUNT(*) AS count FROM announcements WHERE approved=1"),
            "scholarships":  count("SELECT COUNT(*) AS count FROM scholarships WHERE approved=1"),
        },
        "total_users": count("SELECT COUNT(*) AS count FROM users"),
        "total_applications": count("SELECT COUNT(*) AS count FROM applications"),
    })

# ── Notification dispatch helpers (FR 8.1 / FR 8.2) ──────────────────────────
import smtplib
from email.mime.text import MIMEText

SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASS     = os.environ.get("SMTP_PASS", "")
SMTP_FROM     = os.environ.get("SMTP_FROM", "noreply@eduportal.ss")
AT_API_KEY    = os.environ.get("AT_API_KEY", "")   # Africa's Talking
AT_SENDER_ID  = os.environ.get("AT_SENDER_ID", "EduPortal")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success, False if not configured."""
    if not SMTP_HOST or not SMTP_USER:
        return False
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception:
        return False


def send_sms(phone: str, message: str) -> bool:
    """Send SMS via Africa's Talking API. Returns True on success."""
    if not AT_API_KEY:
        return False
    try:
        import urllib.request, urllib.parse, json as _json
        payload = urllib.parse.urlencode({
            "username": "sandbox" if "sandbox" in AT_API_KEY.lower() else "eduportal",
            "to": phone,
            "message": message,
            "from": AT_SENDER_ID,
        }).encode()
        req = urllib.request.Request(
            "https://api.africastalking.com/version1/messaging",
            data=payload,
            headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = _json.loads(resp.read())
            return result.get("SMSMessageData", {}).get("Recipients", [{}])[0].get("status") == "Success"
    except Exception:
        return False


@app.route("/api/notifications/test-email", methods=["POST"])
@require_role("admin")
def api_test_email():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    to   = (data.get("to") or u.get("email") or "").strip()
    if not to:
        return api_err("No recipient email address")
    sent = send_email(to, "EduPortal Test Email", "This is a test email from EduPortal South Sudan.")
    return jsonify({"sent": sent, "message": "Email sent" if sent else "SMTP not configured — check SMTP_HOST, SMTP_USER, SMTP_PASS env vars"})


@app.route("/api/notifications/test-sms", methods=["POST"])
@require_role("admin")
def api_test_sms():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    to   = (data.get("to") or u.get("phone") or "").strip()
    if not to:
        return api_err("No recipient phone number")
    sent = send_sms(to, "EduPortal South Sudan: This is a test SMS notification.")
    return jsonify({"sent": sent, "message": "SMS sent" if sent else "Africa's Talking not configured — set AT_API_KEY env var"})


# ── Health ────────────────────────────────────────────────────────────────────

# ── Forgot / Reset Password ──────────────────────────────────────────────────

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
        import secrets
        token = secrets.token_urlsafe(32)
        execute(
            "INSERT OR REPLACE INTO password_resets (user_id, token, created_at) VALUES (?,?,CURRENT_TIMESTAMP)",
            (user["id"], token),
        )
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
    row = query_one(
        "SELECT * FROM password_resets WHERE user_id=? AND token=? AND datetime(created_at,'+1 hour') > datetime('now')",
        (int(user_id), token),
    )
    if not row:
        return api_err("Invalid or expired reset token", 400)
    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, int(user_id)))
    execute("DELETE FROM password_resets WHERE user_id=?", (int(user_id),))
    return jsonify({"message": "Password reset successfully. You can now sign in."})

# ── Notifications (bell) ──────────────────────────────────────────────────────

@app.route("/api/notifications")
@require_auth
def api_notifications():
    u = request.current_user  # type: ignore[attr-defined]
    today = datetime.now(timezone.utc).date().isoformat()
    # Scholarship deadlines within 7 days
    rows = query_all(
        """SELECT s.id, s.title, s.deadline,
                  CASE WHEN date(s.deadline) = date('now','+1 day') THEN 1
                       WHEN date(s.deadline) <= date('now','+7 days') THEN 7
                       ELSE 0 END AS days_left
           FROM scholarships s
           JOIN applications a ON a.scholarship_id=s.id
           WHERE a.user_id=? AND s.approved=1
             AND date(s.deadline) >= date('now')
             AND date(s.deadline) <= date('now','+7 days')
           ORDER BY s.deadline ASC""",
        (u["id"],),
    )
    # Unread announcements (last 7 days)
    ann = query_all(
        "SELECT id,title,created_at FROM announcements WHERE approved=1 AND datetime(created_at) >= datetime('now','-7 days') ORDER BY created_at DESC LIMIT 5"
    )
    notifications = []
    for r in rows:
        notifications.append({"type": "deadline", "title": f"Deadline soon: {r['title']}", "body": f"Closes {r['deadline']}", "id": r["id"]})
    for a in ann:
        notifications.append({"type": "announcement", "title": a["title"], "body": a["created_at"][:10], "id": a["id"]})
    return jsonify({"items": notifications, "count": len(notifications)})

# ── Admin: onboard school (create + send invite email) ───────────────────────

@app.route("/api/admin/onboard-school", methods=["POST"])
@require_role("admin")
def api_admin_onboard_school():
    import secrets
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    name    = (data.get("name") or "").strip()[:150]
    state   = (data.get("state") or "").strip()[:80]
    county  = (data.get("county") or "").strip()[:80]
    level   = (data.get("level") or "").strip()
    email   = (data.get("email") or "").strip()[:120] or None
    if not all([name, state, county, level]):
        return api_err("name, state, county, and level are required")
    if level not in {"primary", "secondary", "tertiary"}:
        return api_err("level must be primary, secondary, or tertiary")
    if not email:
        return api_err("A contact email is required to send the admin invitation")
    sid = execute(
        """INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,
           email,capacity,status,enrollment,language,boarding,hours,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            (data.get("hours") or "").strip()[:80] or None,
            (data.get("description") or "").strip() or None,
        ),
    )
    log_audit(u["id"], "create_school", "school", sid)
    # Generate invitation token
    token = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO invitations (token,role,ref_id,email,used) VALUES (?,?,?,?,0)",
        (token, "school_admin", sid, email),
    )
    base_url = request.host_url.rstrip("/")
    invite_link = f"{base_url}/accept-invite?token={token}"
    body = (
        f"Hello,\n\n"
        f"You have been invited to manage {name} on EduPortal South Sudan.\n\n"
        f"Click the link below to create your admin account:\n{invite_link}\n\n"
        f"This link is single-use. If you did not expect this email, please ignore it.\n\n"
        f"EduPortal South Sudan"
    )
    email_sent = send_email(email, f"EduPortal — Admin Invitation for {name}", body)
    return jsonify({
        "message": "School created and invitation sent",
        "id": sid,
        "invite_link": invite_link,
        "email_sent": email_sent,
    }), 201


@app.route("/api/admin/onboard-ngo", methods=["POST"])
@require_role("admin")
def api_admin_onboard_ngo():
    import secrets
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
    log_audit(u["id"], "create_ngo", "ngo", ngo_id)
    token = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO invitations (token,role,ref_id,email,used) VALUES (?,?,?,?,0)",
        (token, "ngo_officer", ngo_id, email),
    )
    base_url = request.host_url.rstrip("/")
    invite_link = f"{base_url}/accept-invite?token={token}"
    body = (
        f"Hello,\n\n"
        f"You have been invited to manage {org_name} on EduPortal South Sudan.\n\n"
        f"Click the link below to create your admin account:\n{invite_link}\n\n"
        f"This link is single-use. If you did not expect this email, please ignore it.\n\n"
        f"EduPortal South Sudan"
    )
    email_sent = send_email(email, f"EduPortal — Admin Invitation for {org_name}", body)
    return jsonify({
        "message": "Organisation created and invitation sent",
        "id": ngo_id,
        "invite_link": invite_link,
        "email_sent": email_sent,
    }), 201


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
    inv = query_one(
        "SELECT * FROM invitations WHERE token=? AND used=0",
        (token,),
    )
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
    # Link user to their school or NGO
    if inv["role"] == "school_admin" and inv["ref_id"]:
        execute("UPDATE users SET school_id=? WHERE id=?", (inv["ref_id"], uid))
    # Mark invitation as used
    execute("UPDATE invitations SET used=1 WHERE token=?", (token,))
    user = query_one("SELECT * FROM users WHERE id=?", (uid,))
    return jsonify({"token": _make_token(user), "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}), 201


@app.route("/api/invitations/check")
def api_invitation_check():
    """Returns invitation metadata for a token so the accept page can pre-fill info."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return api_err("token is required")
    inv = query_one("SELECT role,ref_id,email,used FROM invitations WHERE token=?", (token,))
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
    return jsonify({"role": inv["role"], "email": inv["email"], "entity_name": entity_name})


# ── Admin: add school ────────────────────────────────────────────────────────

@app.route("/api/schools", methods=["POST"])
@require_role("admin")
def api_school_create():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    name    = (data.get("name") or "").strip()[:150]
    state   = (data.get("state") or "").strip()[:80]
    county  = (data.get("county") or "").strip()[:80]
    level   = (data.get("level") or "").strip()
    if not all([name, state, county, level]):
        return api_err("name, state, county, and level are required")
    if level not in {"primary", "secondary", "tertiary"}:
        return api_err("level must be primary, secondary, or tertiary")
    sid = execute(
        """INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,
           email,capacity,status,enrollment,language,boarding,hours,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            (data.get("hours") or "").strip()[:80] or None,
            (data.get("description") or "").strip() or None,
        ),
    )
    log_audit(u["id"], "create_school", "school", sid)
    return jsonify({"message": "School created", "id": sid, "invite_link": None}), 201

# ── Admin: delete school ─────────────────────────────────────────────────────

@app.route("/api/schools/<int:school_id>", methods=["DELETE"])
@require_role("admin")
def api_school_delete(school_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    school = query_one("SELECT id FROM schools WHERE id=?", (school_id,))
    if not school:
        return api_err("School not found", 404)
    execute("DELETE FROM admission_requirements WHERE school_id=?", (school_id,))
    execute("DELETE FROM schools WHERE id=?", (school_id,))
    log_audit(u["id"], "delete_school", "school", school_id)
    return jsonify({"message": "School deleted"})

# ── Admin: delete user ────────────────────────────────────────────────────────

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@require_role("admin")
def api_admin_delete_user(user_id: int):
    u = request.current_user  # type: ignore[attr-defined]
    if user_id == u["id"]:
        return api_err("Cannot delete your own account")
    execute("DELETE FROM users WHERE id=?", (user_id,))
    log_audit(u["id"], "delete_user", "user", user_id)
    return jsonify({"message": "User deleted"})

# ── School admin: own school dashboard ───────────────────────────────────────

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
        "SELECT id,title,subject,grade,year,type,file_size,approved,created_at FROM materials "
        "WHERE uploaded_by=? ORDER BY created_at DESC",
        (u["email"] or u["phone"],),
    )
    announcements = query_all(
        "SELECT id,title,body,audience,expires_at,approved,created_at FROM announcements "
        "WHERE source_id=? AND source_type='School' ORDER BY created_at DESC",
        (u["id"],),
    )
    bookmark_count = count(
        "SELECT COUNT(*) AS count FROM bookmarks WHERE item_type='school' AND item_id=?",
        (u["school_id"],),
    )
    return jsonify({
        "school": school,
        "requirements": reqs,
        "materials": materials,
        "announcements": announcements,
        "bookmark_count": bookmark_count,
    })


# ── NGO officer: own organisation dashboard ───────────────────────────────────

@app.route("/api/my-ngo")
@require_role("ngo_officer")
def api_my_ngo():
    u = request.current_user  # type: ignore[attr-defined]
    ngo = query_one(
        "SELECT * FROM ngos WHERE email=? OR phone=?",
        (u.get("email") or "", u.get("phone") or ""),
    )
    scholarships: list = []
    announcements: list = []
    app_count = 0
    if ngo:
        scholarships = query_all(
            "SELECT id,title,description,eligibility,deadline,approved,created_at "
            "FROM scholarships WHERE ngo_id=? ORDER BY created_at DESC",
            (ngo["id"],),
        )
        announcements = query_all(
            "SELECT id,title,body,audience,expires_at,approved,created_at FROM announcements "
            "WHERE source_id=? AND source_type='NGO' ORDER BY created_at DESC",
            (u["id"],),
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
        "application_count": app_count,
    })


@app.route("/api/my-ngo", methods=["PUT"])
@require_role("ngo_officer")
def api_my_ngo_update():
    u    = request.current_user  # type: ignore[attr-defined]
    data = request.get_json(silent=True) or {}
    ngo  = query_one(
        "SELECT * FROM ngos WHERE email=? OR phone=?",
        (u.get("email") or "", u.get("phone") or ""),
    )
    if not ngo:
        execute(
            "INSERT INTO ngos (org_name,contact,email,phone,description,verified) VALUES (?,?,?,?,?,0)",
            (
                (data.get("org_name") or "New Organisation").strip(),
                u["name"],
                u.get("email") or "",
                u.get("phone") or "",
                (data.get("description") or "").strip(),
            ),
        )
    else:
        allowed = ["org_name", "contact", "email", "phone", "description"]
        sets, params = [], []
        for field in allowed:
            if field in data:
                sets.append(f"{field}=?")
                params.append(data[field])
        if sets:
            params.append(ngo["id"])
            execute(f"UPDATE ngos SET {', '.join(sets)} WHERE id=?", tuple(params))  # noqa: S608
    return jsonify({"message": "Organisation profile updated"})


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})

@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return api_err("Not found", 404)
    return redirect(url_for("home"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
