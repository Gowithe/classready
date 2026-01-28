# ==============================================================================
# FILE: models.py
# SQLite models (no ORM) for Teacher Platform MVP
# UPDATED: Classroom, ClassroomStudent, Assignment + GameSession + Practice
# ==============================================================================
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(__file__)

# -----------------------------------------------------------------------------
# Persistent SQLite on Render Disk (or any mounted volume)
# -----------------------------------------------------------------------------
_raw_sqlite_path = os.environ.get("SQLITE_PATH", "").strip()
if _raw_sqlite_path:
    if _raw_sqlite_path.endswith(os.sep) or os.path.isdir(_raw_sqlite_path) or (not _raw_sqlite_path.lower().endswith(".db")):
        DB_PATH = os.path.join(_raw_sqlite_path.rstrip("/\\") , "teacher_platform.db")
    else:
        DB_PATH = _raw_sqlite_path
else:
    DB_PATH = os.path.join(BASE_DIR, "teacher_platform.db")

_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
    except Exception:
        pass
    return conn

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in c.fetchall()]
    return column in cols

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return c.fetchone() is not None

def init_db() -> None:
    conn = get_db()
    c = conn.cursor()

        # ================== Library Subjects ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS library_subjects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      description TEXT DEFAULT '',
      grade_level TEXT DEFAULT '',
      subject_type TEXT DEFAULT 'english',
      icon TEXT DEFAULT '📚',
      color TEXT DEFAULT '#667eea',
      sort_order INTEGER DEFAULT 0,
      is_active INTEGER DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)

    # ================== Library Units ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS library_units (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      unit_number INTEGER DEFAULT 1,
      description TEXT DEFAULT '',
      slides_json TEXT,
      game_json TEXT,
      practice_json TEXT,
      tags TEXT DEFAULT '',
      is_free INTEGER DEFAULT 0,
      estimated_time INTEGER DEFAULT 60,
      view_count INTEGER DEFAULT 0,
      clone_count INTEGER DEFAULT 0,
      rating_sum INTEGER DEFAULT 0,
      rating_count INTEGER DEFAULT 0,
      sort_order INTEGER DEFAULT 0,
      is_active INTEGER DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(subject_id) REFERENCES library_subjects(id)
    )
    """)

    # ================== Library Clones ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS library_clones (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      unit_id INTEGER NOT NULL,
      topic_id INTEGER NOT NULL,
      cloned_at TEXT NOT NULL,
      UNIQUE(user_id, unit_id),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(unit_id) REFERENCES library_units(id),
      FOREIGN KEY(topic_id) REFERENCES topics(id)
    )
    """)

    # ================== Library Ratings ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS library_ratings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      unit_id INTEGER NOT NULL,
      rating INTEGER NOT NULL,
      review TEXT DEFAULT '',
      created_at TEXT NOT NULL,
      UNIQUE(user_id, unit_id),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(unit_id) REFERENCES library_units(id)
    )
    """)

    # ================== Subscription Plans ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS subscription_plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      price INTEGER NOT NULL,
      duration_days INTEGER NOT NULL,
      features_json TEXT DEFAULT '{}',
      is_active INTEGER DEFAULT 1,
      created_at TEXT NOT NULL
    )
    """)

    # ================== User Subscriptions ==================
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_subscriptions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      plan_id INTEGER,
      status TEXT DEFAULT 'active',
      started_at TEXT,
      expires_at TEXT,
      payment_ref TEXT DEFAULT '',
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(plan_id) REFERENCES subscription_plans(id)
    )
    """)

    # ---------------- users ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'teacher',
      created_at TEXT NOT NULL
    )
    """)

    # ---------------- topics ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS topics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      owner_id INTEGER NOT NULL DEFAULT 1,
      name TEXT NOT NULL,
      description TEXT,
      slides_json TEXT,
      topic_type TEXT NOT NULL DEFAULT 'manual',
      pdf_file TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(owner_id) REFERENCES users(id)
    )
    """)

    # ---------------- game_questions ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS game_questions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic_id INTEGER NOT NULL,
      set_no INTEGER NOT NULL,
      tile_no INTEGER NOT NULL DEFAULT 0,
      question TEXT NOT NULL,
      answer TEXT NOT NULL,
      points INTEGER NOT NULL DEFAULT 10,
      created_at TEXT NOT NULL,
      FOREIGN KEY(topic_id) REFERENCES topics(id)
    )
    """)

    # ---------------- practice_questions ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS practice_questions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic_id INTEGER NOT NULL,
      type TEXT NOT NULL DEFAULT 'multiple_choice',
      question TEXT NOT NULL,
      correct_answer TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(topic_id) REFERENCES topics(id)
    )
    """)

    # ---------------- attempt_history ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS attempt_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      topic_id INTEGER NOT NULL,
      score INTEGER NOT NULL,
      total INTEGER NOT NULL,
      percentage REAL NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(topic_id) REFERENCES topics(id)
    )
    """)

    # ---------------- practice_links ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS practice_links (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic_id INTEGER NOT NULL,
      created_by INTEGER NOT NULL,
      token TEXT UNIQUE NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      FOREIGN KEY(topic_id) REFERENCES topics(id),
      FOREIGN KEY(created_by) REFERENCES users(id)
    )
    """)

    # ---------------- practice_submissions ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS practice_submissions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      link_id INTEGER NOT NULL,
      student_name TEXT NOT NULL,
      student_no TEXT DEFAULT '',
      classroom TEXT DEFAULT '',
      answers_json TEXT NOT NULL,
      score INTEGER NOT NULL,
      total INTEGER NOT NULL,
      percentage REAL NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(link_id) REFERENCES practice_links(id)
    )
    """)

    # ---------------- game_sessions ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS game_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic_id INTEGER NOT NULL,
      created_by INTEGER NOT NULL,
      title TEXT NOT NULL DEFAULT 'Classroom Session',
      settings_json TEXT DEFAULT '{}',
      state_json TEXT DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(topic_id) REFERENCES topics(id),
      FOREIGN KEY(created_by) REFERENCES users(id)
    )
    """)

    # ---------------- classrooms ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS classrooms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      owner_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      grade_level TEXT DEFAULT '',
      academic_year TEXT DEFAULT '',
      description TEXT DEFAULT '',
      student_count INTEGER DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY(owner_id) REFERENCES users(id)
    )
    """)

    # ---------------- classroom_students ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS classroom_students (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      classroom_id INTEGER NOT NULL,
      student_no TEXT NOT NULL,
      student_name TEXT NOT NULL,
      nickname TEXT DEFAULT '',
      created_at TEXT NOT NULL,
      FOREIGN KEY(classroom_id) REFERENCES classrooms(id)
    )
    """)

    # ---------------- assignments ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS assignments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      classroom_id INTEGER NOT NULL,
      topic_id INTEGER NOT NULL,
      practice_link_id INTEGER,
      title TEXT NOT NULL,
      description TEXT DEFAULT '',
      due_date TEXT,
      is_active INTEGER DEFAULT 1,
      created_by INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(classroom_id) REFERENCES classrooms(id),
      FOREIGN KEY(topic_id) REFERENCES topics(id),
      FOREIGN KEY(practice_link_id) REFERENCES practice_links(id),
      FOREIGN KEY(created_by) REFERENCES users(id)
    )
    """)

    # ---------------- indexes (performance) ----------------
    # แก้ไขการย่อหน้า (Indentation) ให้ถูกต้อง
    c.execute("CREATE INDEX IF NOT EXISTS idx_topics_owner_id ON topics(owner_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_game_questions_topic_set ON game_questions(topic_id, set_no, tile_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_practice_questions_topic ON practice_questions(topic_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attempt_history_user ON attempt_history(user_id, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_practice_links_topic_user ON practice_links(topic_id, created_by, is_active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_practice_links_token ON practice_links(token)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_practice_submissions_link ON practice_submissions(link_id, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_classroom_students_classroom ON classroom_students(classroom_id, student_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_assignments_classroom ON assignments(classroom_id, created_at)")
    
    conn.commit()

    # ✅ MIGRATIONS (safe)
    if not _column_exists(conn, "topics", "owner_id"):
        c.execute("ALTER TABLE topics ADD COLUMN owner_id INTEGER NOT NULL DEFAULT 1")
        conn.commit()

    if not _column_exists(conn, "practice_submissions", "student_no"):
        c.execute("ALTER TABLE practice_submissions ADD COLUMN student_no TEXT DEFAULT ''")
        conn.commit()

    if not _column_exists(conn, "practice_submissions", "classroom"):
        c.execute("ALTER TABLE practice_submissions ADD COLUMN classroom TEXT DEFAULT ''")
        conn.commit()

    conn.close()

class LibrarySubject:
    """วิชาในคลังบทเรียน"""
    
    @staticmethod
    def create(name: str, description: str = "", grade_level: str = "", 
               subject_type: str = "english", icon: str = "📚", color: str = "#667eea") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO library_subjects (name, description, grade_level, subject_type, icon, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, description, grade_level, subject_type, icon, color, now, now))
        conn.commit()
        subject_id = c.lastrowid
        conn.close()
        return LibrarySubject.get_by_id(subject_id)
    
    @staticmethod
    def get_by_id(subject_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM library_subjects WHERE id = ?", (subject_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    
    @staticmethod
    def get_all_active() -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT s.*, 
                   COUNT(u.id) as unit_count,
                   SUM(CASE WHEN u.is_free = 1 THEN 1 ELSE 0 END) as free_count
            FROM library_subjects s
            LEFT JOIN library_units u ON s.id = u.subject_id AND u.is_active = 1
            WHERE s.is_active = 1
            GROUP BY s.id
            ORDER BY s.sort_order, s.name
        """)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    def update(subject_id: int, **kwargs) -> None:
        conn = get_db()
        c = conn.cursor()
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [subject_id]
        c.execute(f"UPDATE library_subjects SET {sets} WHERE id = ?", values)
        conn.commit()
        conn.close()
    
    @staticmethod
    def delete(subject_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE library_subjects SET is_active = 0 WHERE id = ?", (subject_id,))
        conn.commit()
        conn.close()


class LibraryUnit:
    """บทเรียนในคลัง"""
    
    @staticmethod
    def create(subject_id: int, name: str, unit_number: int = 1, description: str = "",
               slides_json: str = "", game_json: str = "", practice_json: str = "",
               is_free: bool = False, estimated_time: int = 60) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO library_units 
            (subject_id, name, unit_number, description, slides_json, game_json, practice_json, 
             is_free, estimated_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (subject_id, name, unit_number, description, slides_json, game_json, practice_json,
              1 if is_free else 0, estimated_time, now, now))
        conn.commit()
        unit_id = c.lastrowid
        conn.close()
        return LibraryUnit.get_by_id(unit_id)
    
    @staticmethod
    def get_by_id(unit_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT u.*, s.name as subject_name, s.icon as subject_icon
            FROM library_units u
            JOIN library_subjects s ON u.subject_id = s.id
            WHERE u.id = ?
        """, (unit_id,))
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            # Calculate average rating
            d["avg_rating"] = round(d["rating_sum"] / d["rating_count"], 1) if d.get("rating_count", 0) > 0 else 0
            return d
        return None
    
    @staticmethod
    def get_by_subject(subject_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT * FROM library_units 
            WHERE subject_id = ? AND is_active = 1
            ORDER BY unit_number, sort_order
        """, (subject_id,))
        rows = c.fetchall()
        conn.close()
        units = []
        for r in rows:
            d = dict(r)
            d["avg_rating"] = round(d["rating_sum"] / d["rating_count"], 1) if d.get("rating_count", 0) > 0 else 0
            units.append(d)
        return units
    
    @staticmethod
    def get_free_units(limit: int = 10) -> List[Dict[str, Any]]:
        """ดึงบทเรียนฟรีทั้งหมด"""
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT u.*, s.name as subject_name, s.icon as subject_icon
            FROM library_units u
            JOIN library_subjects s ON u.subject_id = s.id
            WHERE u.is_free = 1 AND u.is_active = 1
            ORDER BY u.clone_count DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    def get_popular_units(limit: int = 10) -> List[Dict[str, Any]]:
        """ดึงบทเรียนยอดนิยม"""
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT u.*, s.name as subject_name, s.icon as subject_icon
            FROM library_units u
            JOIN library_subjects s ON u.subject_id = s.id
            WHERE u.is_active = 1
            ORDER BY u.clone_count DESC, u.view_count DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    def increment_view(unit_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE library_units SET view_count = view_count + 1 WHERE id = ?", (unit_id,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def increment_clone(unit_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE library_units SET clone_count = clone_count + 1 WHERE id = ?", (unit_id,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def update(unit_id: int, **kwargs) -> None:
        conn = get_db()
        c = conn.cursor()
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [unit_id]
        c.execute(f"UPDATE library_units SET {sets} WHERE id = ?", values)
        conn.commit()
        conn.close()
    
    @staticmethod
    def search(query: str, subject_id: int = None, free_only: bool = False) -> List[Dict[str, Any]]:
        """ค้นหาบทเรียน"""
        conn = get_db()
        c = conn.cursor()
        sql = """
            SELECT u.*, s.name as subject_name, s.icon as subject_icon
            FROM library_units u
            JOIN library_subjects s ON u.subject_id = s.id
            WHERE u.is_active = 1 AND (u.name LIKE ? OR u.description LIKE ? OR u.tags LIKE ?)
        """
        params = [f"%{query}%", f"%{query}%", f"%{query}%"]
        
        if subject_id:
            sql += " AND u.subject_id = ?"
            params.append(subject_id)
        if free_only:
            sql += " AND u.is_free = 1"
        
        sql += " ORDER BY u.clone_count DESC LIMIT 50"
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]


class UserSubscription:
    """การสมัครสมาชิก Premium"""
    
    @staticmethod
    def create(user_id: int, plan_id: int, duration_days: int, payment_ref: str = "") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow()
        expires = now + timedelta(days=duration_days)
        c.execute("""
            INSERT INTO user_subscriptions (user_id, plan_id, status, started_at, expires_at, payment_ref, created_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (user_id, plan_id, now.isoformat(), expires.isoformat(), payment_ref, now.isoformat()))
        conn.commit()
        sub_id = c.lastrowid
        conn.close()
        return UserSubscription.get_by_id(sub_id)
    
    @staticmethod
    def get_by_id(sub_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM user_subscriptions WHERE id = ?", (sub_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    
    @staticmethod
    def get_active_subscription(user_id: int) -> Optional[Dict[str, Any]]:
        """ดึง subscription ที่ยัง active อยู่"""
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            SELECT us.*, sp.name as plan_name
            FROM user_subscriptions us
            LEFT JOIN subscription_plans sp ON us.plan_id = sp.id
            WHERE us.user_id = ? AND us.status = 'active' AND us.expires_at > ?
            ORDER BY us.expires_at DESC
            LIMIT 1
        """, (user_id, now))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    
    @staticmethod
    def is_premium(user_id: int) -> bool:
        """เช็คว่า user เป็น Premium หรือไม่"""
        sub = UserSubscription.get_active_subscription(user_id)
        return sub is not None
    
    @staticmethod
    def grant_premium(user_id: int, days: int, reason: str = "admin_grant") -> Dict[str, Any]:
        """Admin ให้ Premium แบบไม่ต้องจ่ายเงิน"""
        return UserSubscription.create(user_id, None, days, reason)
    
    @staticmethod
    def cancel(sub_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE user_subscriptions SET status = 'cancelled' WHERE id = ?", (sub_id,))
        conn.commit()
        conn.close()


class LibraryClone:
    """ประวัติการ Clone บทเรียน"""
    
    @staticmethod
    def create(user_id: int, unit_id: int, topic_id: int) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO library_clones (user_id, unit_id, topic_id, cloned_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, unit_id, topic_id, now))
        conn.commit()
        clone_id = c.lastrowid
        conn.close()
        
        # Increment clone count
        LibraryUnit.increment_clone(unit_id)
        
        return {"id": clone_id, "user_id": user_id, "unit_id": unit_id, "topic_id": topic_id}
    
    @staticmethod
    def get_by_user(user_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT lc.*, lu.name as unit_name, t.name as topic_name
            FROM library_clones lc
            JOIN library_units lu ON lc.unit_id = lu.id
            JOIN topics t ON lc.topic_id = t.id
            WHERE lc.user_id = ?
            ORDER BY lc.cloned_at DESC
        """, (user_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    def has_cloned(user_id: int, unit_id: int) -> bool:
        """เช็คว่า user เคย clone unit นี้หรือยัง"""
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM library_clones WHERE user_id = ? AND unit_id = ?", (user_id, unit_id))
        row = c.fetchone()
        conn.close()
        return row is not None


class LibraryRating:
    """Rating บทเรียน"""
    
    @staticmethod
    def rate(user_id: int, unit_id: int, rating: int, review: str = "") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        
        # Check existing rating
        c.execute("SELECT id, rating FROM library_ratings WHERE user_id = ? AND unit_id = ?", (user_id, unit_id))
        existing = c.fetchone()
        
        if existing:
            old_rating = existing[1]
            # Update existing
            c.execute("""
                UPDATE library_ratings SET rating = ?, review = ?, created_at = ?
                WHERE user_id = ? AND unit_id = ?
            """, (rating, review, now, user_id, unit_id))
            # Update unit rating sum
            c.execute("""
                UPDATE library_units SET rating_sum = rating_sum - ? + ?
                WHERE id = ?
            """, (old_rating, rating, unit_id))
        else:
            # Insert new
            c.execute("""
                INSERT INTO library_ratings (user_id, unit_id, rating, review, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, unit_id, rating, review, now))
            # Update unit rating
            c.execute("""
                UPDATE library_units SET rating_sum = rating_sum + ?, rating_count = rating_count + 1
                WHERE id = ?
            """, (rating, unit_id))
        
        conn.commit()
        conn.close()
        return {"user_id": user_id, "unit_id": unit_id, "rating": rating}
    
    @staticmethod
    def get_user_rating(user_id: int, unit_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM library_ratings WHERE user_id = ? AND unit_id = ?", (user_id, unit_id))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None


class SubscriptionPlan:
    """แพ็คเกจสมาชิก"""
    
    @staticmethod
    def get_all_active() -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY price")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    def get_by_id(plan_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscription_plans WHERE id = ?", (plan_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

# =============================================================================
# Models (User, Topic, GameQuestion, etc.)
# =============================================================================

class User:
    @staticmethod
    def create(email: str, password: str, role: str = "teacher") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        password_hash = generate_password_hash(password)
        c.execute("""
            INSERT INTO users (email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
        """, (email.lower(), password_hash, role, now))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return User.get_by_id(user_id)

    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None


class Topic:
    @staticmethod
    def create(owner_id: int, name: str, description: str, slides_json: str, topic_type: str, pdf_file: Optional[str] = None) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO topics (owner_id, name, description, slides_json, topic_type, pdf_file, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (owner_id, name, description, slides_json, topic_type, pdf_file, now))
        conn.commit()
        topic_id = c.lastrowid
        conn.close()
        return Topic.get_by_id(topic_id)

    @staticmethod
    def update(topic_id: int, name: str, description: str, slides_json: str, pdf_file: Optional[str]) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE topics SET name = ?, description = ?, slides_json = ?, pdf_file = ? WHERE id = ?",
                  (name, description, slides_json, pdf_file, topic_id))
        conn.commit()
        conn.close()

    @staticmethod
    def get_by_id(topic_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM topics ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_owner(owner_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM topics WHERE owner_id = ? ORDER BY id DESC", (owner_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete(topic_id: int) -> None:
        GameQuestion.delete_by_topic(topic_id)
        PracticeQuestion.delete_by_topic(topic_id)
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
        conn.close()


class GameQuestion:
    @staticmethod
    def create(topic_id: int, set_no: int, tile_no: int, question: str, answer: str, points: int = 10) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO game_questions (topic_id, set_no, tile_no, question, answer, points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (topic_id, set_no, tile_no, question, answer, points, now))
        conn.commit()
        q_id = c.lastrowid
        conn.close()
        return GameQuestion.get_by_id(q_id)

    @staticmethod
    def get_by_id(q_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM game_questions WHERE id = ?", (q_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_topic_and_set(topic_id: int, set_no: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM game_questions WHERE topic_id = ? AND set_no = ? ORDER BY tile_no, id", (topic_id, set_no))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete_by_topic(topic_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM game_questions WHERE topic_id = ?", (topic_id,))
        conn.commit()
        conn.close()


class PracticeQuestion:
    @staticmethod
    def create(topic_id: int, q_type: str, question: str, correct_answer: str) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO practice_questions (topic_id, type, question, correct_answer, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (topic_id, q_type, question, correct_answer, now))
        conn.commit()
        q_id = c.lastrowid
        conn.close()
        return PracticeQuestion.get_by_id(q_id)

    @staticmethod
    def get_by_topic(topic_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_questions WHERE topic_id = ? ORDER BY id", (topic_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete_by_topic(topic_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM practice_questions WHERE topic_id = ?", (topic_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_by_id(q_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_questions WHERE id = ?", (q_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None


class AttemptHistory:
    @staticmethod
    def create(user_id: int, topic_id: int, score: int, total: int, percentage: float) -> None:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO attempt_history (user_id, topic_id, score, total, percentage, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, topic_id, score, total, percentage, now))
        conn.commit()
        conn.close()

    @staticmethod
    def track_view(user_id: int, topic_id: int) -> None:
        AttemptHistory.create(user_id, topic_id, 0, 0, 0)

    @staticmethod
    def get_recent_by_user(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT ah.topic_id, t.name, MAX(ah.created_at) as last_access
            FROM attempt_history ah
            JOIN topics t ON ah.topic_id = t.id
            WHERE ah.user_id = ?
            GROUP BY ah.topic_id
            ORDER BY last_access DESC
            LIMIT ?
        """, (user_id, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]


class PracticeLink:
    @staticmethod
    def create(topic_id: int, created_by: int, token: str) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            "INSERT INTO practice_links (topic_id, created_by, token, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (topic_id, created_by, token, now)
        )
        conn.commit()
        link_id = c.lastrowid
        conn.close()
        return PracticeLink.get_by_id(link_id)

    @staticmethod
    def get_by_id(link_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_links WHERE id = ?", (link_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_token(token: str) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_links WHERE token = ?", (token,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    # ✅ เพิ่มเมธอดนี้: ดึงลิงก์ล่าสุดของ topic (โดยรวม ทั้ง active/inactive)
    @staticmethod
    def get_by_topic(topic_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM practice_links
            WHERE topic_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (topic_id,),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_latest_active_by_topic_and_user(topic_id: int, created_by: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM practice_links WHERE topic_id = ? AND created_by = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
            (topic_id, created_by)
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def deactivate(link_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE practice_links SET is_active = 0 WHERE id = ?", (link_id,))
        conn.commit()
        conn.close()


class PracticeSubmission:
    @staticmethod
    def create(link_id: int, student_name: str, student_no: str, classroom: str, answers_json: str, score: int, total: int, percentage: float) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO practice_submissions (link_id, student_name, student_no, classroom, answers_json, score, total, percentage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (link_id, student_name, student_no or '', classroom or '', answers_json, score, total, percentage, now))
        conn.commit()
        sub_id = c.lastrowid
        conn.close()
        return PracticeSubmission.get_by_id(sub_id)

    @staticmethod
    def get_by_id(sub_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_submissions WHERE id = ?", (sub_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_link(link_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_submissions WHERE link_id = ? ORDER BY id DESC LIMIT ?", (link_id, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_topic(topic_id: int, limit: int = 1000) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT ps.*, pl.topic_id
            FROM practice_submissions ps
            JOIN practice_links pl ON ps.link_id = pl.id
            WHERE pl.topic_id = ?
            ORDER BY ps.id DESC LIMIT ?
        """, (topic_id, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]


class GameSession:
    @staticmethod
    def create(topic_id: int, created_by: int, title: str, settings_json: str = "{}", state_json: str = "{}") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO game_sessions (topic_id, created_by, title, settings_json, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (topic_id, created_by, title, settings_json, state_json, now, now))
        conn.commit()
        session_id = c.lastrowid
        conn.close()
        return GameSession.get_by_id(session_id)

    @staticmethod
    def get_by_id(session_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_topic(topic_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM game_sessions WHERE topic_id = ? ORDER BY updated_at DESC LIMIT ?", (topic_id, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_latest_by_topic_and_user(topic_id: int, created_by: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM game_sessions WHERE topic_id = ? AND created_by = ? ORDER BY updated_at DESC LIMIT 1",
                  (topic_id, created_by))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(session_id: int, title: str, settings_json: str, state_json: str) -> None:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("UPDATE game_sessions SET title = ?, settings_json = ?, state_json = ?, updated_at = ? WHERE id = ?",
                  (title, settings_json, state_json, now, session_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(session_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM game_sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()


class Classroom:
    @staticmethod
    def create(owner_id: int, name: str, grade_level: str = "", academic_year: str = "", description: str = "") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO classrooms (owner_id, name, grade_level, academic_year, description, student_count, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (owner_id, name, grade_level, academic_year, description, now))
        conn.commit()
        classroom_id = c.lastrowid
        conn.close()
        return Classroom.get_by_id(classroom_id)

    @staticmethod
    def get_by_id(classroom_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM classrooms WHERE id = ?", (classroom_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_owner(owner_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM classrooms WHERE owner_id = ? ORDER BY name", (owner_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(classroom_id: int, name: str, grade_level: str, academic_year: str, description: str) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE classrooms SET name = ?, grade_level = ?, academic_year = ?, description = ? WHERE id = ?",
                  (name, grade_level, academic_year, description, classroom_id))
        conn.commit()
        conn.close()

    @staticmethod
    def update_student_count(classroom_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM classroom_students WHERE classroom_id = ?", (classroom_id,))
        count = c.fetchone()[0]
        c.execute("UPDATE classrooms SET student_count = ? WHERE id = ?", (count, classroom_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(classroom_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM classroom_students WHERE classroom_id = ?", (classroom_id,))
        c.execute("DELETE FROM assignments WHERE classroom_id = ?", (classroom_id,))
        c.execute("DELETE FROM classrooms WHERE id = ?", (classroom_id,))
        conn.commit()
        conn.close()


class ClassroomStudent:
    @staticmethod
    def create(classroom_id: int, student_no: str, student_name: str, nickname: str = "") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO classroom_students (classroom_id, student_no, student_name, nickname, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (classroom_id, student_no, student_name, nickname, now))
        conn.commit()
        student_id = c.lastrowid
        conn.close()
        Classroom.update_student_count(classroom_id)
        return ClassroomStudent.get_by_id(student_id)

    @staticmethod
    def get_by_id(student_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM classroom_students WHERE id = ?", (student_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_classroom(classroom_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM classroom_students WHERE classroom_id = ? ORDER BY CAST(student_no AS INTEGER), student_no", (classroom_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(student_id: int, student_no: str, student_name: str, nickname: str) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE classroom_students SET student_no = ?, student_name = ?, nickname = ? WHERE id = ?",
                  (student_no, student_name, nickname, student_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(student_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT classroom_id FROM classroom_students WHERE id = ?", (student_id,))
        row = c.fetchone()
        classroom_id = row[0] if row else None
        c.execute("DELETE FROM classroom_students WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()
        if classroom_id:
            Classroom.update_student_count(classroom_id)

    @staticmethod
    def bulk_create(classroom_id: int, students: List[Dict[str, str]]) -> int:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        count = 0
        for s in students:
            student_no = (s.get("student_no") or "").strip()
            student_name = (s.get("student_name") or "").strip()
            nickname = (s.get("nickname") or "").strip()
            if student_name:
                c.execute("""
                    INSERT INTO classroom_students (classroom_id, student_no, student_name, nickname, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (classroom_id, student_no, student_name, nickname, now))
                count += 1
        conn.commit()
        conn.close()
        Classroom.update_student_count(classroom_id)
        return count


class Assignment:
    @staticmethod
    def create(classroom_id: int, topic_id: int, practice_link_id: int, title: str, description: str, due_date: str, created_by: int) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO assignments (classroom_id, topic_id, practice_link_id, title, description, due_date, is_active, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (classroom_id, topic_id, practice_link_id, title, description, due_date, created_by, now))
        conn.commit()
        assignment_id = c.lastrowid
        conn.close()
        return Assignment.get_by_id(assignment_id)

    @staticmethod
    def get_by_id(assignment_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_classroom(classroom_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT a.*, t.name as topic_name
            FROM assignments a
            JOIN topics t ON a.topic_id = t.id
            WHERE a.classroom_id = ?
            ORDER BY a.created_at DESC
        """, (classroom_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_owner(owner_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT a.*, t.name as topic_name, c.name as classroom_name
            FROM assignments a
            JOIN topics t ON a.topic_id = t.id
            JOIN classrooms c ON a.classroom_id = c.id
            WHERE a.created_by = ?
            ORDER BY a.created_at DESC
        """, (owner_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete(assignment_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_submissions_status(assignment_id: int) -> Dict[str, Any]:
        assignment = Assignment.get_by_id(assignment_id)
        if not assignment:
            return {"submitted": [], "not_submitted": [], "total": 0}

        classroom_id = assignment["classroom_id"]
        practice_link_id = assignment.get("practice_link_id")
        students = ClassroomStudent.get_by_classroom(classroom_id)

        if not practice_link_id:
            return {"submitted": [], "not_submitted": students, "total": len(students)}

        submissions = PracticeSubmission.get_by_link(practice_link_id)
        submitted_names = set((sub.get("student_name") or "").strip().lower() for sub in submissions)
        submitted_nos = set((sub.get("student_no") or "").strip() for sub in submissions)

        submitted = []
        not_submitted = []

        for student in students:
            name_match = (student.get("student_name") or "").strip().lower() in submitted_names
            no_match = (student.get("student_no") or "").strip() in submitted_nos
            if name_match or no_match:
                for sub in submissions:
                    if ((sub.get("student_name") or "").strip().lower() == (student.get("student_name") or "").strip().lower() or
                        (sub.get("student_no") or "").strip() == (student.get("student_no") or "").strip()):
                        student["submission"] = sub
                        break
                submitted.append(student)
            else:
                not_submitted.append(student)

        return {
            "submitted": submitted,
            "not_submitted": not_submitted,
            "total": len(students),
            "submissions": submissions
        }
