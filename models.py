import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash


# ------------------------------------------------------------
# SQLite connection
# ------------------------------------------------------------

# NOTE:
# - Local: teacher_platform.db (default)
# - Render: you can set DATABASE_URL to a file path like /var/data/teacher_platform.db
DB_PATH = os.environ.get("DATABASE_URL", "teacher_platform.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in c.fetchall()]
    return column in cols


def _safe_alter_add_column(conn: sqlite3.Connection, table: str, column_sql: str) -> None:
    """Add a column if it does not exist. column_sql example: 'plan TEXT DEFAULT "free"'."""
    col_name = column_sql.strip().split()[0]
    if _has_column(conn, table, col_name):
        return
    c = conn.cursor()
    c.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
    conn.commit()


# ------------------------------------------------------------
# DB init + light migrations
# ------------------------------------------------------------


def init_db() -> None:
    conn = get_db()
    c = conn.cursor()

    # -------------------
    # users
    # -------------------
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'teacher',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # subscription columns (migrate if missing)
    _safe_alter_add_column(conn, "users", "plan TEXT NOT NULL DEFAULT 'free'")
    _safe_alter_add_column(conn, "users", "topic_limit INTEGER NOT NULL DEFAULT 5")
    _safe_alter_add_column(conn, "users", "plan_updated_at TEXT")

    # -------------------
    # topics
    # -------------------
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            slides_json TEXT,
            topic_type TEXT DEFAULT 'manual',
            pdf_file TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()

    # If you created topics table before adding owner_id, migrate it.
    # We'll add owner_id as nullable then backfill to 1 (admin) if possible.
    if not _has_column(conn, "topics", "owner_id"):
        _safe_alter_add_column(conn, "topics", "owner_id INTEGER")
        # backfill: choose first admin, else first user, else 0
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE role='admin' ORDER BY id ASC LIMIT 1")
        row = c.fetchone()
        fallback_id = int(row[0]) if row else 0
        if fallback_id == 0:
            c.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            row2 = c.fetchone()
            fallback_id = int(row2[0]) if row2 else 0
        c.execute("UPDATE topics SET owner_id = COALESCE(owner_id, ?)", (fallback_id,))
        conn.commit()

    _safe_alter_add_column(conn, "topics", "topic_type TEXT DEFAULT 'manual'")
    _safe_alter_add_column(conn, "topics", "pdf_file TEXT")

    # -------------------
    # game_questions
    # -------------------
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS game_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            set_no INTEGER NOT NULL,
            tile_no INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 10,
            created_at TEXT NOT NULL,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
        """
    )
    conn.commit()

    # -------------------
    # practice_questions
    # -------------------
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS practice_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            question TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
        """
    )
    conn.commit()

    # -------------------
    # attempt_history
    # -------------------
    c.execute(
        """
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
        """
    )
    conn.commit()

    # -------------------
    # practice_links
    # -------------------
    c.execute(
        """
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
        """
    )
    conn.commit()

    # -------------------
    # practice_submissions
    # -------------------
    c.execute(
        """
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
        """
    )
    conn.commit()

    conn.close()


# ------------------------------------------------------------
# User Model
# ------------------------------------------------------------


class User:
    @staticmethod
    def update_plan(user_id, plan):
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET plan = ? WHERE id = ?",
            (plan, user_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def create(email: str, password: str, role: str = "teacher") -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        pw_hash = generate_password_hash(password)
        c.execute(
            """
            INSERT INTO users (email, password_hash, role, created_at, plan, topic_limit, plan_updated_at)
            VALUES (?, ?, ?, ?, 'free', 5, ?)
            """,
            (email, pw_hash, role, now, now),
        )
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return User.get_by_id(user_id)  # type: ignore

    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_users(limit: int = 500) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, email, role, plan, topic_limit, plan_updated_at, created_at
            FROM users
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def set_plan(user_id: int, plan: str, topic_limit: Optional[int] = None) -> None:
        plan = (plan or "free").strip().lower()
        now = datetime.utcnow().isoformat()
        conn = get_db()
        c = conn.cursor()
        if plan == "pro":
            # topic_limit=None means unlimited; we store a large number for simplicity
            lim = 999999 if topic_limit is None else int(topic_limit)
            c.execute(
                "UPDATE users SET plan = 'pro', topic_limit = ?, plan_updated_at = ? WHERE id = ?",
                (lim, now, user_id),
            )
        else:
            lim = 5 if topic_limit is None else int(topic_limit)
            c.execute(
                "UPDATE users SET plan = 'free', topic_limit = ?, plan_updated_at = ? WHERE id = ?",
                (lim, now, user_id),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def ensure_admin_seed(email: str = "admin@demo.com", password: str = "Admin@12345") -> None:
        """Create a demo admin if it doesn't exist."""
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        if row:
            conn.close()
            return
        now = datetime.utcnow().isoformat()
        pw_hash = generate_password_hash(password)
        c.execute(
            """
            INSERT INTO users (email, password_hash, role, created_at, plan, topic_limit, plan_updated_at)
            VALUES (?, ?, 'admin', ?, 'pro', 999999, ?)
            """,
            (email, pw_hash, now, now),
        )
        conn.commit()
        conn.close()
    


# ------------------------------------------------------------
# Topic Model
# ------------------------------------------------------------


class Topic:
    @staticmethod
    def create(
        owner_id: int,
        name: str,
        description: str,
        slides_json: str,
        topic_type: str = "manual",
        pdf_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO topics (owner_id, name, description, slides_json, topic_type, pdf_file, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (owner_id, name, description, slides_json, topic_type, pdf_file, now),
        )
        conn.commit()
        topic_id = c.lastrowid
        conn.close()
        return Topic.get_by_id(topic_id)  # type: ignore

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
    def count_by_owner(owner_id: int) -> int:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM topics WHERE owner_id = ?", (owner_id,))
        n = int(c.fetchone()[0])
        conn.close()
        return n

    @staticmethod
    def update(topic_id: int, name: str, description: str, slides_json: str, pdf_file: Optional[str]) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            UPDATE topics
            SET name = ?, description = ?, slides_json = ?, pdf_file = ?
            WHERE id = ?
            """,
            (name, description, slides_json, pdf_file, topic_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete(topic_id: int) -> None:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def count_by_owner(owner_id: int) -> int:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM topics WHERE owner_id = ?", (owner_id,))
        row = c.fetchone()
        conn.close()
        return int(row["cnt"] if row and "cnt" in row.keys() else 0)


# ------------------------------------------------------------
# GameQuestion Model
# ------------------------------------------------------------


class GameQuestion:
    @staticmethod
    def create(topic_id: int, set_no: int, tile_no: int, question: str, answer: str, points: int = 10) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO game_questions (topic_id, set_no, tile_no, question, answer, points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (topic_id, set_no, tile_no, question, answer, points, now),
        )
        conn.commit()
        q_id = c.lastrowid
        conn.close()
        return GameQuestion.get_by_id(q_id)  # type: ignore

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
        c.execute(
            """
            SELECT * FROM game_questions
            WHERE topic_id = ? AND set_no = ?
            ORDER BY tile_no ASC, id ASC
            """,
            (topic_id, set_no),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_topic(topic_id: int) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM game_questions
            WHERE topic_id = ?
            ORDER BY set_no ASC, tile_no ASC, id ASC
            """,
            (topic_id,),
        )
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


# ------------------------------------------------------------
# PracticeQuestion Model
# ------------------------------------------------------------


class PracticeQuestion:
    @staticmethod
    def create(topic_id: int, q_type: str, question: str, correct_answer: str) -> Dict[str, Any]:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO practice_questions (topic_id, type, question, correct_answer, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (topic_id, q_type, question, correct_answer, now),
        )
        conn.commit()
        q_id = c.lastrowid
        conn.close()
        return PracticeQuestion.get_by_id(q_id)  # type: ignore

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
        c.execute("SELECT * FROM practice_questions WHERE topic_id = ? ORDER BY id ASC", (topic_id,))
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


# ------------------------------------------------------------
# AttemptHistory Model
# ------------------------------------------------------------


class AttemptHistory:
    @staticmethod
    def create(user_id: int, topic_id: int, score: int, total: int, percentage: float) -> None:
        conn = get_db()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            """
            INSERT INTO attempt_history (user_id, topic_id, score, total, percentage, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, topic_id, score, total, percentage, now),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def track_view(user_id: int, topic_id: int) -> None:
        AttemptHistory.create(user_id, topic_id, 0, 0, 0)

    @staticmethod
    def get_recent_by_user(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            SELECT DISTINCT ah.topic_id, t.name, MAX(ah.created_at) as last_access
            FROM attempt_history ah
            JOIN topics t ON ah.topic_id = t.id
            WHERE ah.user_id = ?
            GROUP BY ah.topic_id
            ORDER BY last_access DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ------------------------------------------------------------
# Public practice links + submissions
# ------------------------------------------------------------


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
        return PracticeLink.get_by_id(link_id)  # type: ignore

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
    def create(
        link_id: int,
        student_name: str,
        answers_json: str,
        score: int,
        total: int,
        percentage: float,
    ) -> Dict[str, Any]:
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
        return PracticeSubmission.get_by_id(sub_id)  # type: ignore

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
