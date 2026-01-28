# ==============================================================================
# LIBRARY SYSTEM - Models
# เพิ่มใน models.py
# ==============================================================================

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json

# (ใช้ get_db() ที่มีอยู่แล้วใน models.py)


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
