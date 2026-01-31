import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("SQLITE_PATH", "teacher_platform.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

now = datetime.utcnow().isoformat()

# ✅ ใส่ code (ห้ามว่าง) + ใช้ features_json ให้ตรงกับ models.py
plans = [
    {
        "code": "premium_monthly",
        "name": "Premium รายเดือน",
        "price": 199,
        "duration_days": 30,
        "features_json": '{"topics": -1, "classrooms": -1, "ai_generate": -1}',
        "is_active": 1,
        "created_at": now,
    },
    {
        "code": "premium_yearly",
        "name": "Premium รายปี",
        "price": 1490,
        "duration_days": 365,
        "features_json": '{"topics": -1, "classrooms": -1, "ai_generate": -1}',
        "is_active": 1,
        "created_at": now,
    },
    {
        "code": "school_10",
        "name": "School License (10 ครู)",
        "price": 9900,
        "duration_days": 365,
        "features_json": '{"topics": -1, "classrooms": -1, "ai_generate": -1, "seats": 10}',
        "is_active": 1,
        "created_at": now,
    },
]

ok_count = 0
for p in plans:
    try:
        # ใช้ UPSERT แบบ SQLite (ต้องมี UNIQUE ที่ code)
        c.execute("""
            INSERT INTO subscription_plans
              (code, name, price, duration_days, features_json, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name,
              price=excluded.price,
              duration_days=excluded.duration_days,
              features_json=excluded.features_json,
              is_active=excluded.is_active
        """, (
            p["code"], p["name"], p["price"], p["duration_days"],
            p["features_json"], p["is_active"], p["created_at"]
        ))
        print(f"✅ เพิ่ม/อัปเดต plan: {p['name']} ({p['code']})")
        ok_count += 1
    except Exception as e:
        print(f"❌ Error inserting {p.get('code')}: {e}")

conn.commit()
conn.close()

print(f"\n✅ เสร็จสิ้น: สำเร็จ {ok_count}/{len(plans)} plans")
