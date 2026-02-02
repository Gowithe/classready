-- ==============================================================================
-- เพิ่ม practice_type ใน practice_links
-- ==============================================================================

-- เพิ่มคอลัมน์ practice_type (mcq, fill, unscramble)
ALTER TABLE practice_links ADD COLUMN practice_type TEXT DEFAULT 'mcq';

-- อัปเดต links ที่มีอยู่แล้วให้เป็น mcq (default)
UPDATE practice_links SET practice_type = 'mcq' WHERE practice_type IS NULL;
