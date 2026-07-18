-- ============================================================
-- EduPortal South Sudan — MySQL 8.0 RBAC migration
-- Run once against eduportal_db:
--   mysql -u root -p eduportal_db < 003_mysql_rbac.sql
-- ============================================================

SET NAMES utf8mb4;
SET foreign_key_checks = 0;

-- ── 1. Core tables (MySQL 8.0 syntax) ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120) NOT NULL,
    email         VARCHAR(120) UNIQUE,
    phone         VARCHAR(30)  UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM(
                    'student',
                    'parent',
                    'teacher',
                    'school_admin',
                    'ngo_officer',
                    'admin'
                  ) NOT NULL DEFAULT 'student',
    state         VARCHAR(80)  NOT NULL DEFAULT '',
    county        VARCHAR(80)  NOT NULL DEFAULT '',
    verified      TINYINT      NOT NULL DEFAULT 1,
    notify_email  TINYINT      NOT NULL DEFAULT 1,
    notify_sms    TINYINT      NOT NULL DEFAULT 1,
    notify_inapp  TINYINT      NOT NULL DEFAULT 1,
    avatar        VARCHAR(500) DEFAULT NULL,
    grade         VARCHAR(20)  DEFAULT '',
    school_name   VARCHAR(150) DEFAULT '',
    child_school  VARCHAR(150) DEFAULT '',
    child_grade   VARCHAR(20)  DEFAULT '',
    subjects      TEXT         DEFAULT NULL,
    institution   VARCHAR(150) DEFAULT '',
    experience_years INT       DEFAULT NULL,
    managed_school VARCHAR(150) DEFAULT '',
    position      VARCHAR(100) DEFAULT '',
    school_id     INT          DEFAULT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS schools (
    id           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(150) NOT NULL,
    state        VARCHAR(80)  NOT NULL,
    county       VARCHAR(80)  NOT NULL,
    level        VARCHAR(30)  NOT NULL,
    type         VARCHAR(20)  NOT NULL DEFAULT 'mixed',
    curriculum   VARCHAR(50)  NOT NULL DEFAULT 'National',
    contact_name VARCHAR(100) NOT NULL DEFAULT '',
    phone        VARCHAR(30)  NOT NULL DEFAULT '',
    email        VARCHAR(120) DEFAULT NULL,
    capacity     INT          DEFAULT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'open',
    enrollment   INT          DEFAULT 0,
    language     VARCHAR(30)  DEFAULT 'English',
    boarding     VARCHAR(20)  DEFAULT 'Day',
    hours        VARCHAR(80)  DEFAULT NULL,
    description  TEXT         DEFAULT NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admission_requirements (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    school_id   INT          NOT NULL,
    item_label  VARCHAR(255) NOT NULL,
    is_required TINYINT      NOT NULL DEFAULT 1,
    notes       TEXT         DEFAULT NULL,
    CONSTRAINT fk_req_school FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS materials (
    id           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title        VARCHAR(255) NOT NULL,
    subject      VARCHAR(80)  NOT NULL,
    grade        VARCHAR(20)  NOT NULL,
    year         SMALLINT     NOT NULL,
    type         VARCHAR(50)  NOT NULL,
    file_size    VARCHAR(30)  DEFAULT NULL,
    preview_text TEXT         DEFAULT NULL,
    file_path    VARCHAR(500) DEFAULT NULL,
    uploaded_by  VARCHAR(120) DEFAULT NULL,
    approved     TINYINT      NOT NULL DEFAULT 0,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS announcements (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    body        TEXT         NOT NULL,
    source_type VARCHAR(30)  NOT NULL,
    source_id   INT          DEFAULT NULL,
    audience    VARCHAR(30)  NOT NULL,
    expires_at  DATE         DEFAULT NULL,
    approved    TINYINT      NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ngos (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    org_name    VARCHAR(150) NOT NULL,
    contact     VARCHAR(100) NOT NULL,
    email       VARCHAR(120) DEFAULT NULL,
    phone       VARCHAR(30)  DEFAULT NULL,
    description TEXT         DEFAULT NULL,
    verified    TINYINT      NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scholarships (
    id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ngo_id        INT          DEFAULT NULL,
    title         VARCHAR(255) NOT NULL,
    description   TEXT         NOT NULL,
    eligibility   TEXT         NOT NULL DEFAULT '',
    deadline      DATE         NOT NULL,
    how_to_apply  TEXT         NOT NULL DEFAULT '',
    required_docs TEXT         DEFAULT NULL,
    external_link VARCHAR(500) DEFAULT NULL,
    approved      TINYINT      NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sch_ngo FOREIGN KEY (ngo_id) REFERENCES ngos(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS applications (
    id             INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id        INT      NOT NULL,
    scholarship_id INT      NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'submitted',
    note           TEXT     DEFAULT NULL,
    applied_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_scholarship (user_id, scholarship_id),
    CONSTRAINT fk_app_user FOREIGN KEY (user_id)        REFERENCES users(id)        ON DELETE CASCADE,
    CONSTRAINT fk_app_sch  FOREIGN KEY (scholarship_id) REFERENCES scholarships(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bookmarks (
    id        INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id   INT      NOT NULL,
    item_type VARCHAR(20) NOT NULL,
    item_id   INT      NOT NULL,
    saved_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bookmark (user_id, item_type, item_id),
    CONSTRAINT fk_bm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_log (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    admin_id    INT          DEFAULT NULL,
    action      VARCHAR(80)  NOT NULL,
    target_type VARCHAR(40)  NOT NULL,
    target_id   INT          DEFAULT NULL,
    note        TEXT         DEFAULT NULL,
    timestamp   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS password_resets (
    user_id    INT          NOT NULL PRIMARY KEY,
    token      VARCHAR(255) NOT NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pr_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 2. Invitations — bcrypt-hashed token (HealthBridge pattern) ───────────────
--
--  token_hash  stores bcrypt(token) so the raw token only lives in the email.
--  token_hint  stores the first 8 chars for fast lookup before bcrypt compare.

CREATE TABLE IF NOT EXISTS invitations (
    id         INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    token_hash VARCHAR(255) NOT NULL,
    token_hint CHAR(8)      NOT NULL,
    role       ENUM(
                 'student','parent','teacher',
                 'school_admin','ngo_officer','admin'
               ) NOT NULL,
    ref_id     INT          DEFAULT NULL,
    email      VARCHAR(120) NOT NULL,
    used       TINYINT      NOT NULL DEFAULT 0,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_inv_hint  (token_hint),
    INDEX idx_inv_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 3. RBAC — role_permissions table ─────────────────────────────────────────
--
--  Each row grants a (role, action) pair.
--  Actions are fine-grained strings checked by require_permission() in Python.
--  The admin role is NOT listed here — it bypasses the table entirely (checked
--  in code) so you never need to enumerate every action for admin.

CREATE TABLE IF NOT EXISTS role_permissions (
    id     INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    role   ENUM(
             'student','parent','teacher',
             'school_admin','ngo_officer','admin'
           ) NOT NULL,
    action VARCHAR(80) NOT NULL,
    UNIQUE KEY uq_role_action (role, action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed default permissions
INSERT IGNORE INTO role_permissions (role, action) VALUES
    -- student
    ('student',      'materials:read'),
    ('student',      'materials:download'),
    ('student',      'materials:stream'),
    ('student',      'schools:read'),
    ('student',      'scholarships:read'),
    ('student',      'announcements:read'),
    ('student',      'applications:create'),
    ('student',      'applications:read_own'),
    ('student',      'applications:withdraw'),
    ('student',      'bookmarks:manage'),
    ('student',      'profile:manage'),
    ('student',      'notifications:read'),

    -- parent  (same read access as student, no applications)
    ('parent',       'materials:read'),
    ('parent',       'materials:download'),
    ('parent',       'schools:read'),
    ('parent',       'scholarships:read'),
    ('parent',       'announcements:read'),
    ('parent',       'bookmarks:manage'),
    ('parent',       'profile:manage'),
    ('parent',       'notifications:read'),

    -- teacher
    ('teacher',      'materials:read'),
    ('teacher',      'materials:download'),
    ('teacher',      'materials:stream'),
    ('teacher',      'materials:submit'),
    ('teacher',      'materials:upload_file'),
    ('teacher',      'schools:read'),
    ('teacher',      'scholarships:read'),
    ('teacher',      'announcements:read'),
    ('teacher',      'bookmarks:manage'),
    ('teacher',      'profile:manage'),
    ('teacher',      'notifications:read'),

    -- school_admin  (everything teacher can do + school management)
    ('school_admin', 'materials:read'),
    ('school_admin', 'materials:download'),
    ('school_admin', 'materials:stream'),
    ('school_admin', 'materials:submit'),
    ('school_admin', 'materials:upload_file'),
    ('school_admin', 'schools:read'),
    ('school_admin', 'schools:update_own'),
    ('school_admin', 'schools:requirements_update'),
    ('school_admin', 'announcements:read'),
    ('school_admin', 'announcements:post'),
    ('school_admin', 'scholarships:read'),
    ('school_admin', 'bookmarks:manage'),
    ('school_admin', 'profile:manage'),
    ('school_admin', 'notifications:read'),
    ('school_admin', 'dashboard:school'),

    -- ngo_officer
    ('ngo_officer',  'materials:read'),
    ('ngo_officer',  'materials:download'),
    ('ngo_officer',  'schools:read'),
    ('ngo_officer',  'scholarships:read'),
    ('ngo_officer',  'scholarships:post'),
    ('ngo_officer',  'announcements:read'),
    ('ngo_officer',  'announcements:post'),
    ('ngo_officer',  'bookmarks:manage'),
    ('ngo_officer',  'profile:manage'),
    ('ngo_officer',  'notifications:read'),
    ('ngo_officer',  'dashboard:ngo');

-- ── 4. schema_migrations tracking ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   VARCHAR(255) NOT NULL PRIMARY KEY,
    applied_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO schema_migrations (filename) VALUES ('003_mysql_rbac.sql');

-- ── 5. Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_users_email            ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone            ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_role             ON users(role);
CREATE INDEX IF NOT EXISTS idx_schools_state          ON schools(state);
CREATE INDEX IF NOT EXISTS idx_apps_user              ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_apps_sch               ON applications(scholarship_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user         ON bookmarks(user_id);
CREATE INDEX IF NOT EXISTS idx_materials_approved     ON materials(approved);
CREATE INDEX IF NOT EXISTS idx_scholarships_approved  ON scholarships(approved);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role  ON role_permissions(role);

SET foreign_key_checks = 1;
