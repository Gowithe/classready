# ==============================================================================
# PATCH: เพิ่ม exercise_type ในระบบ Assignment
# ==============================================================================

# ============ 1. models.py - แก้ไข Assignment.create() ============
# บรรทัด 782 เปลี่ยนจาก:
@staticmethod
def create(classroom_id: int, topic_id: int, practice_link_id: int, title: str, description: str, due_date: str, created_by: int) -> Dict[str, Any]:

# เป็น:
@staticmethod
def create(classroom_id: int, topic_id: int, practice_link_id: int, title: str, description: str, due_date: str, created_by: int, exercise_type: str = "mcq") -> Dict[str, Any]:
    conn = get_db()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO assignments (classroom_id, topic_id, practice_link_id, title, description, due_date, is_active, created_by, created_at, exercise_type)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
    """, (classroom_id, topic_id, practice_link_id, title, description, due_date, created_by, now, exercise_type))
    conn.commit()
    assignment_id = c.lastrowid
    conn.close()
    return Assignment.get_by_id(assignment_id)


# ============ 2. app.py - แก้ไข classroom_assign() ============
# บรรทัด ~1654 เปลี่ยนจาก:
@app.route("/classroom/<int:classroom_id>/assign", methods=["POST"])
@login_required
def classroom_assign(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    topic_id = int(request.form.get("topic_id") or 0)
    if not topic_id:
        flash("กรุณาเลือก Topic", "error")
        return redirect(url_for("classroom_detail", classroom_id=classroom_id))
    topic = Topic.get_by_id(topic_id)
    if not topic: abort(404)
    # Create practice link
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    title = (request.form.get("title") or "").strip() or topic["name"]
    due_date = request.form.get("due_date") or None
    Assignment.create(classroom_id, topic_id, link["id"], title, request.form.get("description") or "", due_date, session["user_id"])
    flash("สั่งงานเรียบร้อย", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

# เป็น:
@app.route("/classroom/<int:classroom_id>/assign", methods=["POST"])
@login_required
def classroom_assign(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    topic_id = int(request.form.get("topic_id") or 0)
    if not topic_id:
        flash("กรุณาเลือก Topic", "error")
        return redirect(url_for("classroom_detail", classroom_id=classroom_id))
    topic = Topic.get_by_id(topic_id)
    if not topic: abort(404)
    
    # Get exercise type
    exercise_type = request.form.get("exercise_type") or "mcq"
    
    # Create practice link
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    title = (request.form.get("title") or "").strip() or topic["name"]
    due_date = request.form.get("due_date") or None
    
    Assignment.create(classroom_id, topic_id, link["id"], title, request.form.get("description") or "", due_date, session["user_id"], exercise_type)
    flash("สั่งงานเรียบร้อย", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))


# ============ 3. Database Migration ============
# รันคำสั่ง SQL นี้เพื่อเพิ่ม column ใหม่:
ALTER TABLE assignments ADD COLUMN exercise_type TEXT DEFAULT 'mcq';


# ============ 4. แสดงประเภทแบบฝึกหัดใน classroom_detail.html ============
# แก้ไขส่วนแสดง assignment (บรรทัด ~239):
<div class="assignment-meta">
  <span>📚 {{ a.topic_name }}</span>
  <span>📋 {% if a.exercise_type == 'fill_blanks' %}Fill Blanks{% elif a.exercise_type == 'unscramble' %}Unscramble{% else %}MCQ{% endif %}</span>
  {% if a.due_date %}<span>⏰ {{ a.due_date[:10] }}</span>{% endif %}
</div>
