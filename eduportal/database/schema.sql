-- EduPortal South Sudan — Database Structure
-- Reference schema matching the SRS data model exactly (MySQL 8.0 syntax).
--
-- This is documentation, not the live application schema. The running app
-- (see ../alembic/versions/) uses table and column names that evolved during
-- development (e.g. users.name, materials, admission_requirements with
-- item_label/is_required). This file is the clean SRS-aligned reference
-- design described in the project documentation.
--
-- Tables are created in dependency order so foreign keys resolve on a
-- fresh import: USERS first, then everything that references it.

CREATE TABLE USERS (
    user_id         INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(150) NOT NULL,
    phone_number    VARCHAR(20),
    role            ENUM('student','parent','teacher','school_admin','ngo_officer','platform_admin') NOT NULL,
    status          ENUM('active','suspended','deleted') NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login      TIMESTAMP NULL
);

CREATE TABLE SCHOOLS (
    school_id        INT AUTO_INCREMENT PRIMARY KEY,
    school_name      VARCHAR(200) NOT NULL,
    state            VARCHAR(100) NOT NULL,
    county           VARCHAR(100) NOT NULL,
    school_type      ENUM('public','private','mission') NOT NULL,
    education_level  ENUM('primary','secondary','both') NOT NULL,
    gender_type      ENUM('mixed','male_only','female_only') NOT NULL,
    contact_phone    VARCHAR(20),
    contact_email    VARCHAR(255),
    address          TEXT,
    description      TEXT,
    status           ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by      INT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (approved_by) REFERENCES USERS(user_id)
);

CREATE TABLE ADMISSION_REQUIREMENTS (
    req_id             INT AUTO_INCREMENT PRIMARY KEY,
    school_id          INT NOT NULL,
    requirements_text  TEXT NOT NULL,
    document_url       VARCHAR(500),
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (school_id) REFERENCES SCHOOLS(school_id)
);

CREATE TABLE STUDY_MATERIALS (
    material_id     INT AUTO_INCREMENT PRIMARY KEY,
    uploaded_by     INT NOT NULL,
    school_id       INT NULL,
    title           VARCHAR(255) NOT NULL,
    material_type   ENUM('past_paper','textbook','notes','other') NOT NULL,
    subject         VARCHAR(100) NOT NULL,
    grade_level     INT NOT NULL,
    file_url        VARCHAR(500) NOT NULL,
    status          ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by     INT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uploaded_by) REFERENCES USERS(user_id),
    FOREIGN KEY (school_id) REFERENCES SCHOOLS(school_id),
    FOREIGN KEY (approved_by) REFERENCES USERS(user_id)
);

CREATE TABLE ANNOUNCEMENTS (
    announcement_id  INT AUTO_INCREMENT PRIMARY KEY,
    posted_by        INT NOT NULL,
    title            VARCHAR(255) NOT NULL,
    content          TEXT NOT NULL,
    source_type      ENUM('school','ngo','ministry','platform') NOT NULL,
    status           ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by      INT NULL,
    posted_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at       TIMESTAMP NULL,
    FOREIGN KEY (posted_by) REFERENCES USERS(user_id),
    FOREIGN KEY (approved_by) REFERENCES USERS(user_id)
);

CREATE TABLE SCHOLARSHIPS (
    scholarship_id   INT AUTO_INCREMENT PRIMARY KEY,
    posted_by        INT NOT NULL,
    title            VARCHAR(255) NOT NULL,
    description      TEXT NOT NULL,
    eligibility      TEXT NOT NULL,
    application_url  VARCHAR(500),
    deadline         DATE,
    status           ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by      INT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (posted_by) REFERENCES USERS(user_id),
    FOREIGN KEY (approved_by) REFERENCES USERS(user_id)
);

CREATE TABLE BOOKMARKS (
    bookmark_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    content_type  ENUM('school','material','announcement','scholarship') NOT NULL,
    content_id    INT NOT NULL,
    saved_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(user_id)
);

CREATE TABLE NOTIFICATIONS (
    notification_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    message          VARCHAR(500) NOT NULL,
    channel          ENUM('email','sms') NOT NULL,
    status           ENUM('sent','failed','pending') NOT NULL DEFAULT 'pending',
    sent_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(user_id)
);

CREATE TABLE AUDIT_LOGS (
    log_id         INT AUTO_INCREMENT PRIMARY KEY,
    admin_id       INT NOT NULL,
    action         VARCHAR(255) NOT NULL,
    target_table   VARCHAR(100) NOT NULL,
    target_id      INT NOT NULL,
    performed_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES USERS(user_id)
);
