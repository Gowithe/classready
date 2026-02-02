import sqlite3
import os

DB_PATH = os.environ.get("SQLITE_PATH", "teacher_platform.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ตรวจสอบว่ามี practice_type แล้วหรือยัง
c.execute("PRAGMA table_info(practice_links)")
columns = [col[1] for col in c.fetchall()]

if 'practice_type' not in columns:
    print("Adding practice_type column...")
    c.execute("ALTER TABLE practice_links ADD COLUMN practice_type TEXT DEFAULT 'mcq'")
    c.execute("UPDATE practice_links SET practice_type = 'mcq' WHERE practice_type IS NULL")
    conn.commit()
    print("✅ เพิ่ม practice_type สำเร็จ!")
else:
    print("✅ practice_type มีอยู่แล้ว")

conn.close()
