from __future__ import annotations

import logging
import subprocess
import sys
import bcrypt

from config.settings import BASE_DIR
from db.connection import get_db

log = logging.getLogger(__name__)


def init_db() -> None:
    """Run Alembic migrations to head, then seed if the database is empty."""
    _run_alembic()
    with get_db() as conn:
        from sqlalchemy import text
        row = conn.execute(text("SELECT COUNT(*) AS count FROM schools")).fetchone()
        if (row[0] if row else 0) == 0:
            _seed(conn)


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


# ── Seed data (runs only on a fresh empty database) ──────────────────────────

def _seed(conn) -> None:
    from sqlalchemy import text

    pw = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt()).decode()
    conn.execute(text(
        "INSERT INTO users (name,email,phone,password_hash,role,state,county,verified) "
        "VALUES (:n,:e,:p,:h,:r,:s,:c,1) ON CONFLICT DO NOTHING"
    ), dict(n="Platform Admin", e="admin@eduportal.ss", p="+211000000000",
            h=pw, r="admin", s="Central Equatoria", c="Juba"))

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
    for s in schools:
        row = conn.execute(text(
            "INSERT INTO schools (name,state,county,level,type,curriculum,contact_name,phone,"
            "email,capacity,status,enrollment,language,boarding,hours,description) "
            "VALUES (:a,:b,:c,:d,:e,:f,:g,:h,:i,:j,:k,:l,:m,:n,:o,:p) RETURNING id"
        ), dict(a=s[0],b=s[1],c=s[2],d=s[3],e=s[4],f=s[5],g=s[6],h=s[7],
                i=s[8],j=s[9],k=s[10],l=s[11],m=s[12],n=s[13],o=s[14],p=s[15])).fetchone()
        school_ids.append(row[0])

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
            "INSERT INTO materials (title,subject,grade,year,type,file_size,preview_text,uploaded_by,approved) "
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
        row = conn.execute(text(
            "INSERT INTO ngos (org_name,contact,email,phone,description,verified) "
            "VALUES (:o,:c,:e,:p,:d,1) RETURNING id"
        ), dict(o=org, c=contact, e=email, p=phone, d=desc)).fetchone()
        ngo_ids.append(row[0])

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
