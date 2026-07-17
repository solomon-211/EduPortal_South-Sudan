CREATE INDEX IF NOT EXISTS idx_users_email   ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone   ON users(phone);
CREATE INDEX IF NOT EXISTS idx_schools_state ON schools(state);
CREATE INDEX IF NOT EXISTS idx_apps_user     ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_apps_sch      ON applications(scholarship_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id);
CREATE INDEX IF NOT EXISTS idx_materials_approved ON materials(approved);
CREATE INDEX IF NOT EXISTS idx_scholarships_approved ON scholarships(approved);
