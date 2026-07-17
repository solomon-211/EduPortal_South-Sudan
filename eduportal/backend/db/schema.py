from __future__ import annotations

import bcrypt

from config.settings import DB_DIR, MIGRATIONS_DIR, MYSQL_DATABASE
from db.connection import get_db, db_engine, adapt_schema, table_columns


# ── Public entry point ────────────────────────────────────────────────────────

def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        mcols = table_columns(db, "materials")
        if mcols and "file_path" not in mcols:
            try:
                db.execute("ALTER TABLE materials ADD COLUMN file_path TEXT")
            except Exception:
                pass

        schema = "\n\n".join(
            p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
        )
        if db_engine() in {"mysql", "postgres"}:
            schema = adapt_schema(schema)
        db.executescript(schema)

        _migrate(db)

        row = db.execute("SELECT COUNT(*) AS count FROM schools").fetchone()
        if (row["count"] if isinstance(row, dict) else row[0]) == 0:
            _seed(db)

        db.commit()


# ── Column migrations ─────────────────────────────────────────────────────────

def _migrate(db) -> None:
    for sql in [
        "ALTER TABLE materials ADD COLUMN file_path TEXT",
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
    ]:
        try:
            db.execute(sql)
        except Exception:
            pass


# ── Seed data ─────────────────────────────────────────────────────────────────

def _seed(db) -> None:
    pw = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt()).decode()
    if db_engine() == "mysql":
        db.execute(
            "INSERT IGNORE INTO users (name,email,phone,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,?,1)",
            ("Platform Admin", "admin@eduportal.ss", "+211000000000", pw, "admin", "Central Equatoria", "Juba"),
        )
    else:
        db.execute(
            "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT DO NOTHING",
            ("Platform Admin", "admin@eduportal.ss", "+211000000000", pw, "admin", "Central Equatoria", "Juba"),
        )

    schools = [
        ("Juba Day Secondary School", "Central Equatoria", "Juba", "secondary", "mixed", "National", "Amina Mayen", "+211 912 000 101", "juba.day@example.com", 1200, "open", 980, "English", "Day", "7:30 AM – 3:30 PM", "A long-running public secondary school serving central Juba."),
        ("Bor Primary School", "Jonglei", "Bor South", "primary", "mixed", "National", "Peter Aken", "+211 912 000 102", "bor.primary@example.com", 800, "open", 640, "English", "Day", "7:00 AM – 1:00 PM", "A community school with broad catchment across Bor South."),
        ("Wau Girls Secondary School", "Western Bahr el Ghazal", "Wau", "secondary", "girls", "National", "Grace Mahad", "+211 912 000 103", "wau.girls@example.com", 900, "open", 725, "English", "Boarding", "8:00 AM – 4:00 PM", "Girls-focused secondary school with boarding support."),
        ("Rumbek Academy", "Lakes", "Rumbek East", "secondary", "mixed", "National", "Deng Atar", "+211 912 000 104", "rumbek.academy@example.com", 1000, "open", 810, "English", "Day", "7:30 AM – 3:30 PM", "Mixed secondary school known for exam preparation."),
        ("Malakal Model School", "Upper Nile", "Malakal", "primary", "mixed", "National", "Hilda Acuil", "+211 912 000 105", "malakal.model@example.com", 700, "limited", 560, "English", "Day", "7:00 AM – 1:00 PM", "A model primary school near the Nile corridor."),
        ("Yambio Community School", "Western Equatoria", "Yambio", "primary", "mixed", "National", "Martin Yel", "+211 912 000 106", "yambio.community@example.com", 650, "open", 520, "English", "Day", "7:00 AM – 1:00 PM", "Community-rooted school with simple admission requirements."),
        ("Kuajok Technical School", "Warrap", "Kuajok", "secondary", "mixed", "National", "Rebecca Chuol", "+211 912 000 107", "kuajok.tech@example.com", 950, "open", 760, "English", "Day", "8:00 AM – 4:00 PM", "Technical learning and practical sciences focus."),
        ("Aweil Girls Primary", "Northern Bahr el Ghazal", "Aweil East", "primary", "girls", "National", "Mayen Chol", "+211 912 000 108", "aweil.girls@example.com", 600, "open", 480, "English", "Day", "7:00 AM – 1:00 PM", "Primary school with strong parent engagement."),
        ("Torit Preparatory School", "Eastern Equatoria", "Torit", "secondary", "mixed", "National", "James Lado", "+211 912 000 109", "torit.prep@example.com", 850, "open", 690, "English", "Day", "7:30 AM – 3:00 PM", "Prepares learners for national examinations."),
        ("Bentiu Bridge School", "Unity", "Bentiu", "primary", "mixed", "National", "Martha Kueth", "+211 912 000 110", "bentiu.bridge@example.com", 500, "open", 410, "English", "Day", "7:00 AM – 1:00 PM", "Stable access point for learning in Unity state."),
    ]
    school_ids: list[int] = []
    for school in schools:
        cur = db.execute(
            "INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,email,capacity,status,enrollment,language,boarding,hours,description) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            school,
        )
        school_ids.append(cur.lastrowid or 0)

    requirement_sets = [
        [("Birth certificate or baptism certificate", 1, "Bring original plus one photocopy."), ("Two passport photos", 1, "Recent photos with plain background."), ("Last report card", 1, "Required for transfer applicants.")],
        [("Child health card", 1, "Only for P1 intake."), ("Copy of parent ID", 1, "Any official identity document accepted.")],
        [("Completed admission form", 1, None), ("Transfer letter", 0, "Needed only when moving from another school."), ("Two passport photos", 1, None)],
    ]
    for i, sid in enumerate(school_ids):
        for label, required, notes in requirement_sets[i % len(requirement_sets)]:
            db.execute(
                "INSERT INTO admission_requirements (school_id,item_label,is_required,notes) VALUES (?,?,?,?)",
                (sid, label, required, notes),
            )

    for title, subject, grade, year, mtype, size, preview in [
        ("Mathematics P8 Past Paper 2024", "Mathematics", "P8", 2024, "past paper", "1.8 MB", "Arithmetic, geometry, and measurement questions."),
        ("English S4 Study Notes", "English", "S4", 2023, "study guide", "900 KB", "Revision notes for comprehension and essay writing."),
        ("Science S6 Teacher Notes", "Science", "S6", 2024, "teacher note", "2.3 MB", "Practical science revision notes for senior learners."),
        ("Social Studies P5 Past Paper", "Social Studies", "P5", 2022, "past paper", "1.1 MB", "A lightweight practice paper for primary learners."),
    ]:
        db.execute(
            "INSERT INTO materials (title,subject,grade,year,type,file_size,preview_text,uploaded_by,approved) VALUES (?,?,?,?,?,?,?,?,1)",
            (title, subject, grade, year, mtype, size, preview, "admin@eduportal.ss"),
        )

    for title, body, source, audience, expires in [
        ("2026 National Exam Registration", "Registration for national exams is open across all states until 30 June.", "Ministry", "students", "2026-06-30"),
        ("School Holiday Notice", "All schools in Jonglei should observe the updated weather-related holiday schedule.", "School", "parents", "2026-06-10"),
        ("Teacher Workshop in Juba", "SSNEC will host a curriculum support workshop for teachers next week.", "SSNEC", "teachers", "2026-05-28"),
    ]:
        db.execute(
            "INSERT INTO announcements (title,body,source_type,audience,expires_at,approved) VALUES (?,?,?,?,?,1)",
            (title, body, source, audience, expires),
        )

    ngo_ids: list[int] = []
    for org, contact, email, phone, desc in [
        ("Future South Sudan Trust", "Grace Atong", "contact@futuress.org", "+211 912 200 111", "Supporting secondary learners across South Sudan since 2018."),
        ("Girls in STEM Initiative", "Luka Bullen", "info@girlsinstem.ss", "+211 912 200 112", "Empowering girls to pursue science and technology careers."),
    ]:
        cur = db.execute(
            "INSERT INTO ngos (org_name,contact,email,phone,description,verified) VALUES (?,?,?,?,?,1)",
            (org, contact, email, phone, desc),
        )
        ngo_ids.append(cur.lastrowid or 0)

    for ngo_id, title, desc, elig, deadline, how, docs, link in [
        (ngo_ids[0], "Secondary School Support Grant", "Partial tuition support for secondary learners with strong attendance.", "Grade 9–12, South Sudan resident, not already funded", "2026-07-20", "Complete the online application and attach your latest report card.", "Report card, birth certificate, recommendation letter", "https://futuress.org/apply"),
        (ngo_ids[1], "Girls STEM Bursary", "Supports girls entering science and technology pathways.", "Female learners in S4–S6, any state", "2026-08-15", "Submit the bursary form and a short motivation letter.", "Motivation letter, school ID, report card", "https://girlsinstem.ss/bursary"),
        (ngo_ids[0], "Rural Materials Pack", "Book and stationery support for learners in remote counties.", "Primary learners in rural counties", "2026-06-25", "Contact your school admin for the referral form.", "Referral form from school admin", None),
    ]:
        db.execute(
            "INSERT INTO scholarships (ngo_id,title,description,eligibility,deadline,how_to_apply,required_docs,external_link,approved) VALUES (?,?,?,?,?,?,?,?,1)",
            (ngo_id, title, desc, elig, deadline, how, docs, link),
        )
