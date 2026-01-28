-- ==============================================================================
-- LIBRARY SYSTEM - Database Schema
-- คลังบทเรียนสำเร็จรูป พร้อม Freemium Model
-- ==============================================================================

-- ตารางวิชา (Subjects)
CREATE TABLE IF NOT EXISTS library_subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- ชื่อวิชา เช่น "English ป.6"
    name_en TEXT,                          -- ชื่อภาษาอังกฤษ
    description TEXT,                      -- คำอธิบายวิชา
    grade_level TEXT,                      -- ระดับชั้น เช่น "ป.6", "ม.1"
    subject_type TEXT DEFAULT 'english',   -- ประเภท: english, math, science, etc.
    cover_image TEXT,                      -- รูปปก
    icon TEXT DEFAULT '📚',                -- Emoji icon
    color TEXT DEFAULT '#667eea',          -- สีธีม
    sort_order INTEGER DEFAULT 0,          -- ลำดับการแสดง
    is_active INTEGER DEFAULT 1,           -- เปิด/ปิดใช้งาน
    created_at TEXT,
    updated_at TEXT
);

-- ตารางบทเรียน (Units)
CREATE TABLE IF NOT EXISTS library_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,           -- FK -> library_subjects
    name TEXT NOT NULL,                    -- ชื่อบท เช่น "Unit 1: Greetings"
    name_th TEXT,                          -- ชื่อภาษาไทย
    description TEXT,                      -- คำอธิบาย
    unit_number INTEGER DEFAULT 1,         -- ลำดับบท
    
    -- เนื้อหา (เก็บเป็น JSON เหมือน topics)
    slides_json TEXT,                      -- Slides data
    game_json TEXT,                        -- Game data (3 sets)
    practice_json TEXT,                    -- Practice MCQ data
    vocabulary_json TEXT,                  -- คำศัพท์แยก (optional)
    
    -- Freemium settings
    is_free INTEGER DEFAULT 0,             -- 1 = ฟรี, 0 = Premium
    preview_slides INTEGER DEFAULT 3,      -- จำนวน slides ที่ดูฟรีได้ (ถ้า is_free=0)
    
    -- Metadata
    estimated_time INTEGER DEFAULT 60,     -- เวลาโดยประมาณ (นาที)
    difficulty TEXT DEFAULT 'medium',      -- easy, medium, hard
    tags TEXT,                             -- tags แยกด้วย comma
    cover_image TEXT,                      -- รูปปกบท
    
    -- Stats
    clone_count INTEGER DEFAULT 0,         -- จำนวนครั้งที่ถูก clone
    view_count INTEGER DEFAULT 0,          -- จำนวนครั้งที่ถูกดู
    rating_sum INTEGER DEFAULT 0,          -- ผลรวมคะแนน rating
    rating_count INTEGER DEFAULT 0,        -- จำนวนคนให้ rating
    
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    
    FOREIGN KEY (subject_id) REFERENCES library_subjects(id)
);

-- ตาราง Subscription Plans
CREATE TABLE IF NOT EXISTS subscription_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- ชื่อแพ็คเกจ เช่น "Premium Monthly"
    description TEXT,
    price REAL NOT NULL,                   -- ราคา (บาท)
    duration_days INTEGER NOT NULL,        -- ระยะเวลา (วัน) เช่น 30, 365
    features TEXT,                         -- ฟีเจอร์ที่ได้ (JSON)
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);

-- ตาราง User Subscriptions
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,              -- FK -> users
    plan_id INTEGER,                       -- FK -> subscription_plans (NULL = manual/admin grant)
    status TEXT DEFAULT 'active',          -- active, expired, cancelled
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    payment_ref TEXT,                      -- อ้างอิงการชำระเงิน
    created_at TEXT,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
);

-- ตาราง Clone History (ติดตามว่าใครเอาบทเรียนไหนไปใช้)
CREATE TABLE IF NOT EXISTS library_clones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,              -- FK -> users
    unit_id INTEGER NOT NULL,              -- FK -> library_units
    topic_id INTEGER NOT NULL,             -- FK -> topics (topic ที่สร้างใหม่)
    cloned_at TEXT,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (unit_id) REFERENCES library_units(id),
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

-- ตาราง Unit Ratings (ให้ครู rate บทเรียน)
CREATE TABLE IF NOT EXISTS library_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,               -- 1-5 ดาว
    review TEXT,                           -- ความคิดเห็น (optional)
    created_at TEXT,
    
    UNIQUE(user_id, unit_id),              -- 1 user = 1 rating per unit
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (unit_id) REFERENCES library_units(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_library_units_subject ON library_units(subject_id);
CREATE INDEX IF NOT EXISTS idx_library_units_free ON library_units(is_free);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_status ON user_subscriptions(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_library_clones_user ON library_clones(user_id);
CREATE INDEX IF NOT EXISTS idx_library_clones_unit ON library_clones(unit_id);

-- ==============================================================================
-- Sample Data: Subscription Plans
-- ==============================================================================
INSERT OR IGNORE INTO subscription_plans (id, name, description, price, duration_days, features, is_active, created_at)
VALUES 
(1, 'Premium Monthly', 'เข้าถึงบทเรียนทั้งหมด 1 เดือน', 199, 30, '{"unlimited_units": true, "no_ads": true}', 1, datetime('now')),
(2, 'Premium Yearly', 'เข้าถึงบทเรียนทั้งหมด 1 ปี (ประหยัด 40%)', 1490, 365, '{"unlimited_units": true, "no_ads": true, "priority_support": true}', 1, datetime('now')),
(3, 'School License', 'สำหรับโรงเรียน (ติดต่อเรา)', 0, 365, '{"unlimited_units": true, "unlimited_teachers": true, "admin_dashboard": true}', 1, datetime('now'));
