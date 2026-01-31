import sqlite3
import os

DB_PATH = os.environ.get("SQLITE_PATH", "teacher_platform.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# สร้างตาราง payment_transactions
c.execute('''
CREATE TABLE IF NOT EXISTS payment_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  plan_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  reference_code TEXT NOT NULL UNIQUE,
  status TEXT DEFAULT 'pending',
  slip_image TEXT,
  easyslip_data TEXT,
  verified_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(plan_id) REFERENCES subscription_plans(id)
)
''')

# สร้าง indexes
c.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_user ON payment_transactions(user_id)")
c.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_ref ON payment_transactions(reference_code)")
c.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_status ON payment_transactions(status)")

conn.commit()
conn.close()

print("✅ สร้างตาราง payment_transactions สำเร็จ!")
