import sqlite3
import os
from datetime import datetime

# หา path ไปยัง database
DB_PATH = os.environ.get("SQLITE_PATH", "teacher_platform.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# เพิ่ม subscription plans
now = datetime.utcnow().isoformat()

plans = [
    (1, 'Premium รายเดือน', 'เข้าถึงทุกฟีเจอร์ ไม่จำกัดการใช้งาน', 199, 30, '{"topics": -1, "classrooms": -1, "ai_generate": -1}', 1, now),
    (2, 'Premium รายปี', 'ประหยัด 40%! เข้าถึงทุกฟีเจอร์ ไม่จำกัด', 1490, 365, '{"topics": -1, "classrooms": -1, "ai_generate": -1}', 1, now),
    (3, 'School License (10 ครู)', 'สำหรับโรงเรียน 10 บัญชี', 9900, 365, '{"topics": -1, "classrooms": -1, "ai_generate": -1, "seats": 10}', 1, now),
]

for plan in plans:
    try:
        c.execute("""
            INSERT OR REPLACE INTO subscription_plans 
            (id, name, description, price, duration_days, features, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, plan)
        print(f"✅ เพิ่ม plan: {plan[1]}")
    except Exception as e:
        print(f"❌ Error: {e}")

conn.commit()
conn.close()

print("\n✅ เพิ่ม subscription plans สำเร็จ!")
