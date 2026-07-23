from __future__ import annotations

import logging
import os
import subprocess
import sys
import bcrypt

from settings import BASE_DIR
from db_connection import get_db, engine

log = logging.getLogger(__name__)


def init_db() -> None:
    """Run Alembic migrations to head, then bootstrap an admin account (always)
    and demo content (only when explicitly requested via SEED_DEMO_DATA)."""
    _run_alembic()
    with get_db() as conn:
        from sqlalchemy import text
        _ensure_admin_account(conn)
        if os.environ.get("SEED_DEMO_DATA", "").strip().lower() in {"1", "true", "yes"}:
            row = conn.execute(text("SELECT COUNT(*) AS count FROM schools")).fetchone()
            if (row[0] if row else 0) == 0:
                _seed_demo_content(conn)


def _ensure_admin_account(conn) -> None:
    """Create a platform admin account if none exists yet, so a freshly-migrated,
    otherwise-empty database is still usable. Override the defaults via
    ADMIN_EMAIL / ADMIN_PASSWORD in .env before first run in any shared environment."""
    from sqlalchemy import text

    existing = conn.execute(text("SELECT COUNT(*) AS count FROM users WHERE role='admin'")).scalar()
    if existing:
        return
    email = os.environ.get("ADMIN_EMAIL", "admin@eduportal.ss").strip()
    password = os.environ.get("ADMIN_PASSWORD", "Admin1234!")
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    ignore_kw = "INSERT IGNORE" if engine.dialect.name == "mysql" else "INSERT OR IGNORE"
    conn.execute(text(
        f"{ignore_kw} INTO users (name,email,password_hash,role,state,county,verified) "
        "VALUES (:n,:e,:h,'admin',:s,:c,1)"
    ), dict(n="Platform Admin", e=email, h=pw, s="Central Equatoria", c="Juba"))
    log.warning(
        "No admin account existed — created %s with the default/configured password. "
        "Set ADMIN_EMAIL and ADMIN_PASSWORD in .env for anything beyond local development.",
        email,
    )


def _run_alembic() -> None:
    """Invoke `alembic upgrade head` programmatically."""
    alembic_ini = BASE_DIR / "alembic.ini"
    if not alembic_ini.exists():
        log.warning("alembic.ini not found at %s — skipping migrations", alembic_ini)
        return
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        log.critical("Alembic migration failed:\n%s", result.stderr)
        raise RuntimeError(f"Alembic upgrade head failed: {result.stderr}")
    if result.stdout:
        log.info("Alembic: %s", result.stdout.strip())


# Demo content — only loaded when SEED_DEMO_DATA is set (see init_db above).
# Useful for local development and demos; never runs by default.

def _seed_demo_content(conn) -> None:
    from sqlalchemy import text

    schools = [
        ("Juba Day Secondary School", "Central Equatoria", "Juba", "secondary", "mixed", "National", "Amina Mayen", "+211 912 000 101", "juba.day@example.com", 1200, "open", 980, "English", "Day", "public", "7:30 AM – 3:30 PM", "A long-running public secondary school serving central Juba."),
        ("Bor Primary School", "Jonglei", "Bor South", "primary", "mixed", "National", "Peter Aken", "+211 912 000 102", "bor.primary@example.com", 800, "open", 640, "English", "Day", "public", "7:00 AM – 1:00 PM", "A community school with broad catchment across Bor South."),
        ("Wau Girls Secondary School", "Western Bahr el Ghazal", "Wau", "secondary", "girls", "National", "Grace Mahad", "+211 912 000 103", "wau.girls@example.com", 900, "open", 725, "English", "Boarding", "private", "8:00 AM – 4:00 PM", "Girls-focused secondary school with boarding support."),
        ("Rumbek Academy", "Lakes", "Rumbek East", "secondary", "mixed", "National", "Deng Atar", "+211 912 000 104", "rumbek.academy@example.com", 1000, "open", 810, "English", "Day", "private", "7:30 AM – 3:30 PM", "Mixed secondary school known for exam preparation."),
        ("Malakal Model School", "Upper Nile", "Malakal", "primary", "mixed", "National", "Hilda Acuil", "+211 912 000 105", "malakal.model@example.com", 700, "limited", 560, "English", "Day", "public", "7:00 AM – 1:00 PM", "A model primary school near the Nile corridor."),
        ("Yambio Community School", "Western Equatoria", "Yambio", "primary", "mixed", "National", "Martin Yel", "+211 912 000 106", "yambio.community@example.com", 650, "open", 520, "English", "Day", "public", "7:00 AM – 1:00 PM", "Community-rooted school with simple admission requirements."),
        ("Kuajok Technical School", "Warrap", "Kuajok", "secondary", "mixed", "National", "Rebecca Chuol", "+211 912 000 107", "kuajok.tech@example.com", 950, "open", 760, "English", "Day", "public", "8:00 AM – 4:00 PM", "Technical learning and practical sciences focus."),
        ("Aweil Girls Primary", "Northern Bahr el Ghazal", "Aweil East", "primary", "girls", "National", "Mayen Chol", "+211 912 000 108", "aweil.girls@example.com", 600, "open", 480, "English", "Day", "public", "7:00 AM – 1:00 PM", "Primary school with strong parent engagement."),
        ("Torit Preparatory School", "Eastern Equatoria", "Torit", "secondary", "mixed", "National", "James Lado", "+211 912 000 109", "torit.prep@example.com", 850, "open", 690, "English", "Day", "private", "7:30 AM – 3:00 PM", "Prepares learners for national examinations."),
        ("Bentiu Bridge School", "Unity", "Bentiu", "primary", "mixed", "National", "Martha Kueth", "+211 912 000 110", "bentiu.bridge@example.com", 500, "open", 410, "English", "Day", "public", "7:00 AM – 1:00 PM", "Stable access point for learning in Unity state."),
    ]
    school_ids: list[int] = []
    for s in schools:
        result = conn.execute(text(
            "INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,"
            "email,capacity,status,enrollment,language,boarding,ownership,hours,description) "
            "VALUES (:a,:b,:c,:d,:e,:f,:g,:h,:i,:j,:k,:l,:m,:n,:o,:p,:q)"
        ), dict(a=s[0],b=s[1],c=s[2],d=s[3],e=s[4],f=s[5],g=s[6],h=s[7],
                i=s[8],j=s[9],k=s[10],l=s[11],m=s[12],n=s[13],o=s[14],p=s[15],q=s[16]))
        school_ids.append(result.lastrowid)

    requirement_sets = [
        [("Birth certificate or baptism certificate", True, "Bring original plus one photocopy."),
         ("Two passport photos", True, "Recent photos with plain background."),
         ("Last report card", True, "Required for transfer applicants.")],
        [("Child health card", True, "Only for P1 intake."),
         ("Copy of parent ID", True, "Any official identity document accepted.")],
        [("Completed admission form", True, None),
         ("Transfer letter", False, "Needed only when moving from another school."),
         ("Two passport photos", True, None)],
    ]
    for i, sid in enumerate(school_ids):
        for label, required, notes in requirement_sets[i % len(requirement_sets)]:
            conn.execute(text(
                "INSERT INTO admission_requirements (school_id,item_label,is_required,notes) "
                "VALUES (:s,:l,:r,:n)"
            ), dict(s=sid, l=label, r=int(required), n=notes))

    for title, subject, grade, year, mtype, size, preview in [
        ("Mathematics P8 Past Paper 2024", "Mathematics", "P8", 2024, "past paper", "1.8 MB", "Arithmetic, geometry, and measurement questions."),
        ("English S4 Study Notes", "English", "S4", 2023, "study guide", "900 KB", "Revision notes for comprehension and essay writing."),
        ("Science S6 Teacher Notes", "Science", "S6", 2024, "teacher note", "2.3 MB", "Practical science revision notes for senior learners."),
        ("Social Studies P5 Past Paper", "Social Studies", "P5", 2022, "past paper", "1.1 MB", "A lightweight practice paper for primary learners."),
    ]:
        conn.execute(text(
            "INSERT INTO materials (title,subject,grade,`year`,type,file_size,preview_text,uploaded_by,approved) "
            "VALUES (:t,:s,:g,:y,:mt,:fs,:pv,:ub,1)"
        ), dict(t=title, s=subject, g=grade, y=year, mt=mtype, fs=size, pv=preview, ub="admin@eduportal.ss"))

    for title, body, source, audience, expires in [
        ("2026 National Exam Registration", "Registration for national exams is open across all states until 30 June.", "Ministry", "students", "2026-06-30"),
        ("School Holiday Notice", "All schools in Jonglei should observe the updated weather-related holiday schedule.", "School", "parents", "2026-06-10"),
        ("Teacher Workshop in Juba", "SSNEC will host a curriculum support workshop for teachers next week.", "SSNEC", "teachers", "2026-05-28"),
    ]:
        conn.execute(text(
            "INSERT INTO announcements (title,body,source_type,audience,expires_at,approved) "
            "VALUES (:t,:b,:s,:a,:e,1)"
        ), dict(t=title, b=body, s=source, a=audience, e=expires))

    ngo_ids: list[int] = []
    for org, contact, email, phone, desc in [
        ("Future South Sudan Trust", "Grace Atong", "contact@futuress.org", "+211 912 200 111", "Supporting secondary learners across South Sudan since 2018."),
        ("Girls in STEM Initiative", "Luka Bullen", "info@girlsinstem.ss", "+211 912 200 112", "Empowering girls to pursue science and technology careers."),
    ]:
        result = conn.execute(text(
            "INSERT INTO ngos (org_name,contact,email,phone,description,verified) "
            "VALUES (:o,:c,:e,:p,:d,1)"
        ), dict(o=org, c=contact, e=email, p=phone, d=desc))
        ngo_ids.append(result.lastrowid)

    for ngo_id, title, desc, elig, deadline, how, docs, link in [
        (ngo_ids[0], "Secondary School Support Grant", "Partial tuition support for secondary learners with strong attendance.", "Grade 9–12, South Sudan resident, not already funded", "2026-07-20", "Complete the online application and attach your latest report card.", "Report card, birth certificate, recommendation letter", "https://futuress.org/apply"),
        (ngo_ids[1], "Girls STEM Bursary", "Supports girls entering science and technology pathways.", "Female learners in S4–S6, any state", "2026-08-15", "Submit the bursary form and a short motivation letter.", "Motivation letter, school ID, report card", "https://girlsinstem.ss/bursary"),
        (ngo_ids[0], "Rural Materials Pack", "Book and stationery support for learners in remote counties.", "Primary learners in rural counties", "2026-06-25", "Contact your school admin for the referral form.", "Referral form from school admin", None),
    ]:
        conn.execute(text(
            "INSERT INTO scholarships (ngo_id,title,description,eligibility,deadline,"
            "how_to_apply,required_docs,external_link,approved) "
            "VALUES (:ni,:t,:d,:e,:dl,:h,:rd,:el,1)"
        ), dict(ni=ngo_id, t=title, d=desc, e=elig, dl=deadline, h=how, rd=docs, el=link))

    _seed_demo_accounts(conn, school_ids[0], ngo_ids[0])


def _seed_demo_accounts(conn, sample_school_id: int, sample_ngo_id: int) -> None:
    """One login per role, all sharing the password below, so every dashboard
    can be exercised manually without registering fresh accounts each time."""
    from sqlalchemy import text

    pw = bcrypt.hashpw(b"Demo1234!", bcrypt.gensalt()).decode()
    accounts = [
        dict(n="Student Demo", e="student@eduportal.ss", p="+211912300101", r="student",
             s="Central Equatoria", c="Juba", grade="S4", school_name="Juba Day Secondary School"),
        dict(n="Parent Demo", e="parent@eduportal.ss", p="+211912300102", r="parent",
             s="Central Equatoria", c="Juba", child_school="Juba Day Secondary School", child_grade="P6"),
        dict(n="Teacher Demo", e="teacher@eduportal.ss", p="+211912300103", r="teacher",
             s="Central Equatoria", c="Juba", subjects="Mathematics, Physics", institution="Juba Day Secondary School"),
    ]
    for a in accounts:
        conn.execute(text(
            "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified,"
            "grade,school_name,child_school,child_grade,subjects,institution) "
            "VALUES (:n,:e,:p,:h,:r,:s,:c,1,:grade,:school_name,:child_school,:child_grade,:subjects,:institution)"
        ), dict(
            n=a["n"], e=a["e"], p=a["p"], h=pw, r=a["r"], s=a["s"], c=a["c"],
            grade=a.get("grade", ""), school_name=a.get("school_name", ""),
            child_school=a.get("child_school", ""), child_grade=a.get("child_grade", ""),
            subjects=a.get("subjects", ""), institution=a.get("institution", ""),
        ))

    # school_admin is scoped to a school via school_id — manages the first seeded school
    conn.execute(text(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified,"
        "managed_school,school_id) VALUES (:n,:e,:p,:h,'school_admin',:s,:c,1,:ms,:sid)"
    ), dict(n="School Admin Demo", e="schooladmin@eduportal.ss", p="+211912300104",
            h=pw, s="Central Equatoria", c="Juba", ms="Juba Day Secondary School", sid=sample_school_id))

    # ngo_officer resolves its NGO by matching email/phone against the ngos table,
    # so this account's email must match the seeded NGO's contact email.
    ngo_email = conn.execute(text("SELECT email FROM ngos WHERE id=:id"), dict(id=sample_ngo_id)).scalar()
    conn.execute(text(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) "
        "VALUES (:n,:e,:p,:h,'ngo_officer',:s,:c,1)"
    ), dict(n="NGO Officer Demo", e=ngo_email, p="+211912200111", h=pw, s="Central Equatoria", c="Juba"))

    # org_publisher resolves its organization through a used invitation record.
    org_id = conn.execute(text(
        "SELECT id FROM organizations WHERE name LIKE '%Ministry of General Education%' LIMIT 1"
    )).scalar()
    result = conn.execute(text(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) "
        "VALUES (:n,:e,:p,:h,'org_publisher',:s,:c,1)"
    ), dict(n="Org Publisher Demo", e="orgpublisher@eduportal.ss", p="+211912300105",
            h=pw, s="Central Equatoria", c="Juba"))
    if org_id:
        conn.execute(text(
            "INSERT INTO invitations (token_hash,token_hint,role,ref_id,email,used) "
            "VALUES ('seed-unused-hash','seed0000','org_publisher',:oid,:email,1)"
        ), dict(oid=org_id, email="orgpublisher@eduportal.ss"))
