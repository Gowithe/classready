# ==============================================================================
# FILE: models.py
# SQLite models (no ORM) for Teacher Platform MVP
# UPDATED: Classroom, ClassroomStudent, Assignment + GameSession + Practice
# ==============================================================================
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(__file__)

# -----------------------------------------------------------------------------
# Persistent SQLite on Render Disk (or any mounted volume)
#
# Set env var SQLITE_PATH to a FILE path, e.g.
#   SQLITE_PATH=/var/data/teacher_platform.db
#
# If SQLITE_PATH points to a directory, we will create teacher_platform.db inside it.
# -----------------------------------------------------------------------------
_raw_sqlite_path = os.environ.get("SQLITE_PATH", "").strip()
if _raw_sqlite_path:
    # If user gives a directory path, place db file inside it
    if _raw_sqlite_path.endswith(os.sep) or os.path.isdir(_raw_sqlite_path) or (not _raw_sqlite_path.lower().endswith(".db")):
        DB_PATH = os.path.join(_raw_sqlite_path.rstrip("/\\") , "teacher_platform.db")
    else:
        DB_PATH = _raw_sqlite_path
else:
    DB_PATH = os.path.join(BASE_DIR, "teacher_platform.db")

# Ensure folder exists (important for Render Disk mount path)
_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)


def get_db() -> sqlite3.Connection:
    """
    SQLite connection with pragmas tuned for web apps:
    - WAL mode: better concurrency for reads/writes
    - busy_timeout: wait a bit instead of 'database is locked'
    - foreign_keys: enforce FK constraints
    """
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,  # Flask can use threads depending on server
    )
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
    except Exception:
        # If PRAGMA fails for any reason, still return a usable connection
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

    # ---------------- classrooms (NEW!) ----------------
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

    # ---------------- classroom_students (NEW!) ----------------
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

    # ---------------- assignments (NEW!) ----------------
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

    # =======================
    # ✅ MIGRATIONS (safe)
    # =======================
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


# =============================================================================
# User Model
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


# =============================================================================
# Topic Model
# =============================================================================
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
    def update_owner(topic_id: int, owner_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE topics SET owner_id = ? WHERE id = ?", (owner_id, topic_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(topic_id: int) -> None:
        GameQuestion.delete_by_topic(topic_id)
        PracticeQuestion.delete_by_topic(topic_id)
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
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


# =============================================================================
# GameQuestion Model
# =============================================================================
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


# =============================================================================
# PracticeQuestion Model
# =============================================================================
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
    def get_by_id(q_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_questions WHERE id = ?", (q_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

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


# =============================================================================
# AttemptHistory Model
# =============================================================================
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


# =============================================================================
# Practice Links + Submissions
# =============================================================================
class PracticeLink:
    @staticmethod
    def create(topic_id: int, created_by: int, token: str) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO practice_links (topic_id, created_by, token, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                  (topic_id, created_by, token, now))
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

    @staticmethod
    def get_latest_active_by_topic_and_user(topic_id: int, created_by: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM practice_links WHERE topic_id = ? AND created_by = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
                  (topic_id, created_by))
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


# =============================================================================
# GameSession Model
# =============================================================================
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


# =============================================================================
# Classroom Model (NEW!)
# =============================================================================
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
        # Delete students first
        c.execute("DELETE FROM classroom_students WHERE classroom_id = ?", (classroom_id,))
        # Delete assignments
        c.execute("DELETE FROM assignments WHERE classroom_id = ?", (classroom_id,))
        # Delete classroom
        c.execute("DELETE FROM classrooms WHERE id = ?", (classroom_id,))
        conn.commit()
        conn.close()


# =============================================================================
# ClassroomStudent Model (NEW!)
# =============================================================================
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
        # Update count
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
        # Get classroom_id first
        c.execute("SELECT classroom_id FROM classroom_students WHERE id = ?", (student_id,))
        row = c.fetchone()
        classroom_id = row[0] if row else None
        # Delete
        c.execute("DELETE FROM classroom_students WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()
        # Update count
        if classroom_id:
            Classroom.update_student_count(classroom_id)

    @staticmethod
    def delete_by_classroom(classroom_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM classroom_students WHERE classroom_id = ?", (classroom_id,))
        conn.commit()
        conn.close()
        Classroom.update_student_count(classroom_id)

    @staticmethod
    def bulk_create(classroom_id: int, students: List[Dict[str, str]]) -> int:
        """Create multiple students at once. Returns count of created."""
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


# =============================================================================
# Assignment Model (NEW!)
# =============================================================================
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
    def update(assignment_id: int, title: str, description: str, due_date: str, is_active: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE assignments SET title = ?, description = ?, due_date = ?, is_active = ? WHERE id = ?",
                  (title, description, due_date, is_active, assignment_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(assignment_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_submissions_status(assignment_id: int) -> Dict[str, Any]:
        """Get submission status for an assignment"""
        assignment = Assignment.get_by_id(assignment_id)
        if not assignment:
            return {"submitted": [], "not_submitted": [], "total": 0}

        classroom_id = assignment["classroom_id"]
        practice_link_id = assignment.get("practice_link_id")

        # Get all students in classroom
        students = ClassroomStudent.get_by_classroom(classroom_id)

        if not practice_link_id:
            return {"submitted": [], "not_submitted": students, "total": len(students)}

        # Get submissions for this practice link
        submissions = PracticeSubmission.get_by_link(practice_link_id)
        submitted_names = set()
        submitted_nos = set()
        for sub in submissions:
            submitted_names.add((sub.get("student_name") or "").strip().lower())
            submitted_nos.add((sub.get("student_no") or "").strip())

        submitted = []
        not_submitted = []

        for student in students:
            name_match = (student.get("student_name") or "").strip().lower() in submitted_names
            no_match = (student.get("student_no") or "").strip() in submitted_nos
            if name_match or no_match:
                # Find the submission
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
