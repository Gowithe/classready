# ==============================================================================
# FILE: models.py
# SQLite models (no ORM) for Teacher Platform MVP
# UPDATED: add ownership (owner_id) + migrations
# ==============================================================================
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.environ.get("SQLITE_PATH", os.path.join(BASE_DIR, "teacher_platform.db"))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in c.fetchall()]  # (cid, name, type, notnull, dflt_value, pk)
    return column in cols


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
    # ✅ NEW: owner_id (topic belongs to a teacher)
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
      answers_json TEXT NOT NULL,
      score INTEGER NOT NULL,
      total INTEGER NOT NULL,
      percentage REAL NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(link_id) REFERENCES practice_links(id)
    )
    """)

    conn.commit()

    # =======================
    # ✅ MIGRATIONS (safe)
    # =======================
    # If topics table existed before without owner_id -> add it
    if not _column_exists(conn, "topics", "owner_id"):
        c.execute("ALTER TABLE topics ADD COLUMN owner_id INTEGER NOT NULL DEFAULT 1")
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
    def create(
        owner_id: int,
        name: str,
        description: str,
        slides_json: str,
        topic_type: str,
        pdf_file: Optional[str] = None
    ) -> Dict[str, Any]:
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
        c.execute("""
            UPDATE topics
            SET name = ?, description = ?, slides_json = ?, pdf_file = ?
            WHERE id = ?
        """, (name, description, slides_json, pdf_file, topic_id))
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

    @staticmethod
    def get_by_id_and_owner(topic_id: int, owner_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM topics WHERE id = ? AND owner_id = ?", (topic_id, owner_id))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None


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
        c.execute("""
            SELECT * FROM game_questions
            WHERE topic_id = ? AND set_no = ?
            ORDER BY tile_no, id
        """, (topic_id, set_no))
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
# PracticeQuestion Model (MCQ only)
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
# Public Practice Links + Submissions
# =============================================================================
class PracticeLink:
    @staticmethod
    def create(topic_id: int, created_by: int, token: str) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO practice_links (topic_id, created_by, token, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (topic_id, created_by, token, now),
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

    @staticmethod
    def get_latest_active_by_topic_and_user(topic_id: int, created_by: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM practice_links
            WHERE topic_id = ? AND created_by = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (topic_id, created_by),
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
    def create(link_id: int, student_name: str, answers_json: str, score: int, total: int, percentage: float) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO practice_submissions (link_id, student_name, answers_json, score, total, percentage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (link_id, student_name, answers_json, score, total, percentage, now),
        )
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
    def get_by_link(link_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM practice_submissions
            WHERE link_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (link_id, limit),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
