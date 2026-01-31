-- ==============================================================================
-- FREEMIUM SYSTEM - Database Migration
-- รัน SQL นี้ใน database
-- ==============================================================================

-- 1. สร้างตาราง user_usage สำหรับ tracking การใช้งาน
CREATE TABLE IF NOT EXISTS user_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL UNIQUE,
  ai_generate_count INTEGER DEFAULT 0,
  ai_generate_reset_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

-- 2. สร้าง index
CREATE INDEX IF NOT EXISTS idx_user_usage_user ON user_usage(user_id);

-- 3. อัปเดต subscription plans (ถ้ายังไม่มี)
INSERT OR IGNORE INTO subscription_plans (id, name, description, price, duration_days, features, is_active, created_at) VALUES
(1, 'Premium รายเดือน', 'เข้าถึงทุกฟีเจอร์ ไม่จำกัดการใช้งาน', 199, 30, '{"topics": -1, "classrooms": -1, "ai_generate": -1, "library_premium": true, "export": true}', 1, datetime('now')),
(2, 'Premium รายปี', 'ประหยัด 40%! เข้าถึงทุกฟีเจอร์ ไม่จำกัด', 1490, 365, '{"topics": -1, "classrooms": -1, "ai_generate": -1, "library_premium": true, "export": true}', 1, datetime('now')),
(3, 'School License (10 ครู)', 'สำหรับโรงเรียน 10 บัญชี', 9900, 365, '{"topics": -1, "classrooms": -1, "ai_generate": -1, "library_premium": true, "export": true, "seats": 10}', 1, datetime('now'));

-- 4. ตรวจสอบว่าสร้างสำเร็จ
-- SELECT * FROM user_usage LIMIT 5;
-- SELECT * FROM subscription_plans;
