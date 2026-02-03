"""
RESET PRACTICE LINKS - ลบ links และ submissions เก่า
==============================================================================
⚠️ คำเตือน: Script นี้จะลบข้อมูลคะแนนแบบฝึกหัดทั้งหมด!
ใช้เมื่อต้องการให้ระบบสร้าง links ใหม่ที่มี practice_type ถูกต้อง
==============================================================================
"""

import sqlite3
import os

DB_PATH = os.environ.get("SQLITE_PATH", "teacher_platform.db")

def reset_practice_links():
    print("=" * 60)
    print("⚠️  คำเตือน: Script นี้จะลบข้อมูลคะแนนแบบฝึกหัดทั้งหมด!")
    print("=" * 60)
    
    confirm = input("พิมพ์ 'YES' เพื่อยืนยัน: ")
    if confirm != "YES":
        print("❌ ยกเลิก")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # นับก่อนลบ
    c.execute("SELECT COUNT(*) FROM practice_submissions")
    sub_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM practice_links")
    link_count = c.fetchone()[0]
    
    print(f"\n📊 ข้อมูลปัจจุบัน:")
    print(f"   - Practice Links: {link_count}")
    print(f"   - Submissions: {sub_count}")
    
    # ลบ
    c.execute("DELETE FROM practice_submissions")
    c.execute("DELETE FROM practice_links")
    conn.commit()
    
    print(f"\n✅ ลบเรียบร้อย!")
    print(f"   - ลบ Links: {link_count} รายการ")
    print(f"   - ลบ Submissions: {sub_count} รายการ")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("📌 ขั้นตอนต่อไป:")
    print("   1. ครูกดปุ่ม 'สร้างลิงก์' ใหม่สำหรับแต่ละแบบฝึกหัด")
    print("   2. นักเรียนทำแบบฝึกหัดใหม่")
    print("   3. หน้า All Scores จะแสดง Tabs ถูกต้อง")
    print("=" * 60)

if __name__ == "__main__":
    reset_practice_links()
