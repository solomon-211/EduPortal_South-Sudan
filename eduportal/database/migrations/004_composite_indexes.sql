-- ============================================================
-- EduPortal South Sudan — composite indexes
-- Applied by Alembic migration 0003_composite_indexes.py
-- These cover the most frequent filtered queries in app.py
-- ============================================================

-- announcements: approved feed ordered by date
CREATE INDEX IF NOT EXISTS idx_ann_approved_date
    ON announcements(approved, created_at DESC);

-- materials: filtered browse (approved + subject + grade)
CREATE INDEX IF NOT EXISTS idx_mat_approved_subject_grade
    ON materials(approved, subject, grade);

-- materials: year + type for exam paper browsing
CREATE INDEX IF NOT EXISTS idx_mat_year_type
    ON materials(year DESC, type);

-- scholarships: approved feed ordered by deadline
CREATE INDEX IF NOT EXISTS idx_sch_approved_deadline
    ON scholarships(approved, deadline ASC);

-- applications: user history ordered by date
CREATE INDEX IF NOT EXISTS idx_apps_user_date
    ON applications(user_id, applied_at DESC);

-- applications: status filter for admin queue
CREATE INDEX IF NOT EXISTS idx_apps_status
    ON applications(status);

-- bookmarks: type filter per user (e.g. all saved schools)
CREATE INDEX IF NOT EXISTS idx_bookmarks_user_type
    ON bookmarks(user_id, item_type);

-- password_resets: token lookup via hint
CREATE INDEX IF NOT EXISTS idx_pr_token_hint
    ON password_resets(token);

-- schools: name search
CREATE INDEX IF NOT EXISTS idx_schools_name
    ON schools(name);

-- schools: multi-column filter (state + level + type)
CREATE INDEX IF NOT EXISTS idx_schools_state_level_type
    ON schools(state, level, type);
