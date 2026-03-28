"""
Run this script ONCE on Render Shell to update subscription plan prices.
Command: python3 update_prices.py
"""
import sqlite3
import os

DB_PATH = os.environ.get("DATABASE_PATH", "database.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Show current plans
print("=== BEFORE ===")
c.execute("SELECT * FROM subscription_plans ORDER BY id")
for row in c.fetchall():
    print(f"  ID={row['id']}  code={row['code']}  name={row['name']}  price={row['price']}  days={row['duration_days']}")

# Update monthly: 199 -> 59
c.execute("UPDATE subscription_plans SET price = 59 WHERE code = 'monthly' OR (duration_days <= 31 AND price > 59)")
print(f"\nUpdated monthly plans: {c.rowcount} row(s)")

# Update yearly: 1490 -> 599
c.execute("UPDATE subscription_plans SET price = 599 WHERE code = 'yearly' OR code = 'annual' OR (duration_days >= 360 AND price > 599)")
print(f"Updated yearly plans: {c.rowcount} row(s)")

conn.commit()

# Show updated plans
print("\n=== AFTER ===")
c.execute("SELECT * FROM subscription_plans ORDER BY id")
for row in c.fetchall():
    print(f"  ID={row['id']}  code={row['code']}  name={row['name']}  price={row['price']}  days={row['duration_days']}")

conn.close()
print("\nDone!")
