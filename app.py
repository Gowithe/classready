# ==============================================================================
# FILE: app.py
# Teacher Platform MVP (Flask + SQLite)
# UPDATED: Classroom Management + Assignments + Game Sessions + Practice Export
# ==============================================================================

import os
import json
import secrets
import traceback
import base64
import csv
from io import BytesIO, StringIO
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort, Response
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from models import (
    get_db, init_db, User, Topic, GameQuestion, PracticeQuestion, AttemptHistory,
    PracticeLink, PracticeSubmission, GameSession, Classroom, ClassroomStudent, Assignment,
)
from ai_generator import generate_lesson_bundle

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename): return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
def allowed_image(filename): return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

with app.app_context():
    init_db()
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@teacherplatform.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    if not User.get_by_email(admin_email):
        User.create(admin_email, admin_password, "admin")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        user = User.get_by_id(session["user_id"])
        if not user or user.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

def _is_admin(): return session.get("role") == "admin"
def _can_access_topic(topic): return _is_admin() or int(topic.get("owner_id") or 0) == int(session.get("user_id") or 0)
def _get_topic_or_404(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic: abort(404)
    if not _can_access_topic(topic): abort(403)
    return topic

def _wants_json_response(): return request.path.startswith("/api/") or "application/json" in (request.headers.get("Accept") or "").lower()
def _json_error(message, status=400): return jsonify({"ok": False, "error": message}), status


# ==============================================================================
# Auth & Landing
# ==============================================================================
@app.route("/")
def landing(): return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm_password") or "").strip()
        if not email or not password:
            flash("Email and password required.", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if User.get_by_email(email):
            flash("Email already registered.", "error")
            return render_template("register.html")
        User.create(email, password, "teacher")
        flash("Registration successful!", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        user = User.get_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename): return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ==============================================================================
# Dashboard
# ==============================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    my_topics = Topic.get_by_owner(user_id)
    all_topics = Topic.get_all() if _is_admin() else my_topics
    recent = AttemptHistory.get_recent_by_user(user_id, limit=5)
    classrooms = Classroom.get_by_owner(user_id)
    return render_template("dashboard.html", my_topics=my_topics, topics=all_topics, recent=recent, classrooms=classrooms)

@app.route("/topic/<int:topic_id>")
@login_required
def topic_detail(topic_id):
    topic = _get_topic_or_404(topic_id)
    AttemptHistory.track_view(session["user_id"], topic_id)
    is_owner = int(topic.get("owner_id") or 0) == int(session["user_id"])
    has_game = len(GameQuestion.get_by_topic_and_set(topic_id, 1) or []) > 0
    has_practice = len(PracticeQuestion.get_by_topic(topic_id) or []) > 0
    has_slides = False
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
            has_slides = len(slides) > 0
        except: pass
    return render_template("topic_detail.html", topic=topic, is_owner=is_owner, is_admin=_is_admin(), has_game=has_game, has_practice=has_practice, has_slides=has_slides)


# ==============================================================================
# My Topics CRUD
# ==============================================================================
@app.route("/my/topics/create", methods=["GET", "POST"])
@login_required
def my_create_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=None, mode="create")
        topic = Topic.create(session["user_id"], name, description, json.dumps({"slides": []}, ensure_ascii=False), "manual", None)
        return redirect(url_for("my_edit_topic", topic_id=topic["id"]))
    return render_template("my_topic_edit.html", topic=None, mode="create")

@app.route("/my/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@login_required
def my_edit_topic(topic_id):
    topic = _get_topic_or_404(topic_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        slides_json = (request.form.get("slides_json") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=topic, mode="edit")
        try: json.loads(slides_json)
        except:
            flash("Invalid JSON.", "error")
            return render_template("my_topic_edit.html", topic=topic, mode="edit")
        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename and allowed_file(file.filename):
            safe_name = secure_filename(file.filename)
            final_name = f"user{session['user_id']}_topic{topic_id}_{secrets.token_hex(6)}_{safe_name}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], final_name))
            pdf_filename = final_name
        Topic.update(topic_id, name, description, slides_json, pdf_filename)
        flash("Saved.", "success")
        return redirect(url_for("topic_detail", topic_id=topic_id))
    return render_template("my_topic_edit.html", topic=topic, mode="edit")

@app.route("/my/topics/<int:topic_id>/delete", methods=["POST"])
@login_required
def my_delete_topic(topic_id):
    _get_topic_or_404(topic_id)
    Topic.delete(topic_id)
    return redirect(url_for("dashboard"))


# ==============================================================================
# Slides
# ==============================================================================
@app.route("/topic/<int:topic_id>/slides")
@login_required
def view_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    if topic.get("pdf_file"):
        return render_template("slides_pdf_presentation.html", topic=topic, pdf_url=url_for("uploaded_file", filename=topic["pdf_file"]))
    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except: pass
    return render_template("slides_viewer.html", topic=topic, slides=slides)

@app.route("/topic/<int:topic_id>/slides/edit")
@login_required
def edit_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    return render_template("slides_editor.html", topic=topic)

@app.route("/api/topic/<int:topic_id>/slides", methods=["POST"])
@login_required
def api_save_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    data = request.get_json(silent=True) or {}
    slides = data.get("slides", [])
    processed = []
    for i, slide in enumerate(slides):
        ps = dict(slide)
        img_url = slide.get("image_url", "")
        if img_url and img_url.startswith("data:image"):
            try:
                header, b64 = img_url.split(",", 1)
                ext = "png" if "png" in header else "gif" if "gif" in header else "jpg"
                fn = f"slide_img_{topic_id}_{i}_{secrets.token_hex(6)}.{ext}"
                with open(os.path.join(app.config["UPLOAD_FOLDER"], fn), "wb") as f:
                    f.write(base64.b64decode(b64))
                ps["image_url"] = url_for("uploaded_file", filename=fn)
            except: pass
        processed.append(ps)
    Topic.update(topic_id, topic["name"], topic["description"], json.dumps({"slides": processed}, ensure_ascii=False), topic.get("pdf_file"))
    return jsonify({"ok": True})


# ==============================================================================
# Game
# ==============================================================================
@app.route("/topic/<int:topic_id>/game")
@login_required
def game(topic_id):
    topic = _get_topic_or_404(topic_id)
    last_session = GameSession.get_latest_by_topic_and_user(topic_id, session["user_id"])
    return render_template("game.html", topic=topic, last_session=last_session)

@app.route("/api/game/<int:topic_id>/sets")
@login_required
def api_game_sets(topic_id):
    _get_topic_or_404(topic_id)
    sets_data = {}
    for set_no in range(1, 4):
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            sets_data[str(set_no)] = [{"id": q["id"], "tile_no": q["tile_no"], "question": q["question"], "answer": q["answer"], "points": q["points"]} for q in questions]
    return jsonify(sets_data)

@app.route("/api/game/<int:topic_id>/sessions", methods=["GET", "POST"])
@login_required
def api_game_sessions(topic_id):
    _get_topic_or_404(topic_id)
    if request.method == "GET":
        return jsonify({"ok": True, "sessions": GameSession.get_by_topic(topic_id)})
    data = request.get_json(silent=True) or {}
    sess = GameSession.create(topic_id, session["user_id"], data.get("title") or "Session", json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True, "session": sess})

@app.route("/api/game/session/<int:session_id>")
@login_required
def api_game_session_get(session_id):
    sess = GameSession.get_by_id(session_id)
    return jsonify({"ok": True, "session": sess}) if sess else _json_error("Not found", 404)

@app.route("/api/game/session/<int:session_id>/save", methods=["POST"])
@login_required
def api_game_session_save(session_id):
    sess = GameSession.get_by_id(session_id)
    if not sess: return _json_error("Not found", 404)
    data = request.get_json(silent=True) or {}
    GameSession.update(session_id, data.get("title") or sess["title"], json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True})


# ==============================================================================
# Practice Helpers
# ==============================================================================
def _normalize_practice_questions(rows):
    out = []
    for r in rows:
        q = dict(r)
        prompt, choices = "", []
        raw = q.get("question") or ""
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                prompt = (obj.get("prompt") or "").strip()
                choices = [str(x) for x in (obj.get("choices") or [])]
            else: prompt = str(obj)
        except: prompt = str(raw)
        out.append({"id": q.get("id"), "prompt": prompt, "choices": choices, "correct_answer": q.get("correct_answer") or ""})
    return out

def _build_practice_pdf(topic_title, questions, include_answers=False):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    mx, y, lh, mw = 2*cm, h-2*cm, 14, w-4*cm
    def draw(lines, y0):
        y = y0
        for ln in lines:
            if y < 2*cm: c.showPage(); y = h-2*cm
            c.drawString(mx, y, ln); y -= lh
        return y
    c.setFont("Helvetica-Bold", 16)
    y = draw([f"Practice: {topic_title}"], y)
    c.setFont("Helvetica", 11)
    y = draw(["Name: ________________________   Class: __________", ""], y)
    for i, q in enumerate(questions, 1):
        c.setFont("Helvetica-Bold", 12)
        y = draw(simpleSplit(f"{i}. {q.get('prompt','')}", "Helvetica-Bold", 12, mw), y)
        c.setFont("Helvetica", 11)
        ch = q.get("choices") or []
        if len(ch) == 4:
            for lab, cv in zip(["A","B","C","D"], ch):
                y = draw(simpleSplit(f"   ({lab}) {cv}", "Helvetica", 11, mw), y)
        if include_answers: y = draw([f"   Answer: {q.get('correct_answer','')}"], y)
        y = draw([""], y)
    c.showPage(); c.save()
    return buf.getvalue()


# ==============================================================================
# Practice
# ==============================================================================
@app.route("/topic/<int:topic_id>/practice")
@login_required
def practice(topic_id):
    topic = _get_topic_or_404(topic_id)
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    student_url = (request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])) if link else None
    return render_template("practice.html", topic=topic, questions=questions, student_url=student_url)

@app.route("/api/practice/<int:topic_id>/submit", methods=["POST"])
@login_required
def api_practice_submit(topic_id):
    _get_topic_or_404(topic_id)
    data = request.get_json() or {}
    answers = data.get("answers", {})
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    score, total, feedback = 0, len(questions), {}
    for q in questions:
        qid = str(q["id"])
        ua = (answers.get(qid, "") or "").strip().lower()
        ca = (q.get("correct_answer") or "").strip().lower()
        correct = ua == ca
        if correct: score += 1
        feedback[qid] = {"is_correct": correct, "user_answer": answers.get(qid, ""), "correct_answer": q.get("correct_answer")}
    pct = (score/total*100) if total else 0
    AttemptHistory.create(session["user_id"], topic_id, score, total, pct)
    return jsonify({"score": score, "total": total, "percentage": pct, "feedback": feedback})

@app.route("/api/practice/<int:topic_id>/link", methods=["POST"])
@login_required
def api_practice_create_link(topic_id):
    _get_topic_or_404(topic_id)
    old = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    if old: PracticeLink.deactivate(old["id"])
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    return jsonify({"url": request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])})

@app.route("/topic/<int:topic_id>/practice/pdf")
@login_required
def practice_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)
    include_answers = request.args.get("answers") == "1"
    pdf = _build_practice_pdf(topic["name"], _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id)), include_answers)
    return (pdf, 200, {"Content-Type": "application/pdf", "Content-Disposition": f"attachment; filename=practice_{topic_id}.pdf"})

@app.route("/topic/<int:topic_id>/practice/scores")
@login_required
def practice_scores(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.id DESC LIMIT 1000", (topic_id,))
    submissions = [dict(r) for r in c.fetchall()]
    conn.close()
    classrooms = sorted(set(s.get("classroom") or "" for s in submissions if s.get("classroom")))
    return render_template("practice_scores.html", topic=topic, submissions=submissions, classrooms=classrooms)

@app.route("/topic/<int:topic_id>/practice/scores/csv")
@login_required
def practice_scores_csv(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.classroom,ps.student_no", (topic_id,))
    rows = c.fetchall()
    conn.close()
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["#", "Name", "No", "Class", "Score", "Total", "%", "Time"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["student_name"], r["student_no"] or "", r["classroom"] or "", r["score"], r["total"], f"{r['percentage']:.0f}%", r["created_at"]])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=scores_{topic_id}.csv"})

@app.route("/topic/<int:topic_id>/practice/scores/excel")
@login_required
def practice_scores_excel(topic_id):
    topic = _get_topic_or_404(topic_id)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    except: return redirect(url_for("practice_scores_csv", topic_id=topic_id))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.classroom,ps.student_no", (topic_id,))
    rows = c.fetchall()
    conn.close()
    wb = Workbook()
    ws = wb.active
    ws.title = "Scores"
    hf, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="667eea")
    bd = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    ws.merge_cells('A1:H1')
    ws['A1'] = f"Practice Scores: {topic['name']}"
    ws['A1'].font = Font(bold=True, size=14)
    for col, h in enumerate(["#", "Name", "No", "Class", "Score", "Total", "%", "Time"], 1):
        cell = ws.cell(3, col, h)
        cell.font, cell.fill, cell.border = hf, hfill, bd
    for i, r in enumerate(rows, 1):
        for col, v in enumerate([i, r["student_name"], r["student_no"] or "", r["classroom"] or "", r["score"], r["total"], f"{r['percentage']:.0f}%", str(r["created_at"])[:19]], 1):
            cell = ws.cell(i+3, col, v)
            cell.border = bd
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=scores_{topic_id}.xlsx"})


# ==============================================================================
# Public Practice
# ==============================================================================
@app.route("/p/<token>")
def public_practice(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link.get("is_active"): return render_template("error.html", error_code=404, error_msg="ลิงก์หมดอายุ"), 404
    topic = Topic.get_by_id(link["topic_id"])
    if not topic: return render_template("error.html", error_code=404, error_msg="Topic not found"), 404
    return render_template("practice_public.html", topic=topic, questions=_normalize_practice_questions(PracticeQuestion.get_by_topic(topic["id"])), token=token)

@app.route("/api/p/<token>/submit", methods=["POST"])
def api_public_practice_submit(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link.get("is_active"): return jsonify({"error": "Invalid link"}), 404
    data = request.get_json() or {}
    name = (data.get("student_name") or "").strip()
    if not name: return jsonify({"error": "Name required"}), 400
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(link["topic_id"]))
    answers = data.get("answers", {})
    score, total, feedback = 0, len(questions), {}
    for q in questions:
        qid = str(q["id"])
        ua = (answers.get(qid, "") or "").strip().lower()
        ca = (q.get("correct_answer") or "").strip().lower()
        correct = ua == ca
        if correct: score += 1
        feedback[qid] = {"is_correct": correct, "user_answer": answers.get(qid, ""), "correct_answer": q.get("correct_answer")}
    pct = (score/total*100) if total else 0
    PracticeSubmission.create(link["id"], name, data.get("student_no") or "", data.get("classroom") or "", json.dumps({"answers": answers}), score, total, pct)
    return jsonify({"score": score, "total": total, "percentage": pct, "feedback": feedback})


# ==============================================================================
# Classrooms
# ==============================================================================
@app.route("/classrooms")
@login_required
def classrooms():
    user_id = session["user_id"]
    cls_list = Classroom.get_by_owner(user_id)
    total_students = sum(c.get("student_count") or 0 for c in cls_list)
    assignments = Assignment.get_by_owner(user_id)
    # Add assignment count to each classroom
    for c in cls_list:
        c["assignment_count"] = len([a for a in assignments if a["classroom_id"] == c["id"]])
    return render_template("classrooms.html", classrooms=cls_list, total_students=total_students, total_assignments=len(assignments))

@app.route("/classrooms/create", methods=["POST"])
@login_required
def classroom_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("กรุณาระบุชื่อห้อง", "error")
        return redirect(url_for("classrooms"))
    Classroom.create(session["user_id"], name, request.form.get("grade_level") or "", request.form.get("academic_year") or "", request.form.get("description") or "")
    flash("สร้างห้องเรียนแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>")
@login_required
def classroom_detail(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    students = ClassroomStudent.get_by_classroom(classroom_id)
    assignments = Assignment.get_by_classroom(classroom_id)
    topics = Topic.get_by_owner(session["user_id"])
    # Get submission stats for each assignment
    submission_stats = {}
    for a in assignments:
        status = Assignment.get_submissions_status(a["id"])
        submission_stats[a["id"]] = {"submitted": len(status["submitted"]), "not_submitted": len(status["not_submitted"])}
    return render_template("classroom_detail.html", classroom=cls, students=students, assignments=assignments, topics=topics, submission_stats=submission_stats)

@app.route("/classroom/<int:classroom_id>/edit", methods=["POST"])
@login_required
def classroom_edit(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    Classroom.update(classroom_id, request.form.get("name") or cls["name"], request.form.get("grade_level") or "", request.form.get("academic_year") or "", request.form.get("description") or "")
    flash("บันทึกแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>/delete", methods=["POST"])
@login_required
def classroom_delete(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    Classroom.delete(classroom_id)
    flash("ลบห้องเรียนแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>/add-student", methods=["POST"])
@login_required
def classroom_add_student(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    name = (request.form.get("student_name") or "").strip()
    if name:
        ClassroomStudent.create(classroom_id, request.form.get("student_no") or "", name, request.form.get("nickname") or "")
        flash("เพิ่มนักเรียนแล้ว", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/classroom/<int:classroom_id>/import-students", methods=["POST"])
@login_required
def classroom_import_students(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    text = request.form.get("student_list") or ""
    students = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        parts = line.split("\t")
        if len(parts) >= 2:
            students.append({"student_no": parts[0].strip(), "student_name": parts[1].strip()})
        else:
            students.append({"student_no": "", "student_name": parts[0].strip()})
    count = ClassroomStudent.bulk_create(classroom_id, students)
    flash(f"Import {count} คนเรียบร้อย", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/classroom/student/<int:student_id>/edit", methods=["POST"])
@login_required
def classroom_student_edit(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s: abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    ClassroomStudent.update(student_id, request.form.get("student_no") or "", request.form.get("student_name") or s["student_name"], request.form.get("nickname") or "")
    return redirect(url_for("classroom_detail", classroom_id=s["classroom_id"]))

@app.route("/classroom/student/<int:student_id>/delete", methods=["POST"])
@login_required
def classroom_student_delete(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s: abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    classroom_id = s["classroom_id"]
    ClassroomStudent.delete(student_id)
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

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

@app.route("/assignment/<int:assignment_id>")
@login_required
def assignment_detail(assignment_id):
    a = Assignment.get_by_id(assignment_id)
    if not a: abort(404)
    cls = Classroom.get_by_id(a["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    topic = Topic.get_by_id(a["topic_id"])
    status = Assignment.get_submissions_status(assignment_id)
    practice_link = PracticeLink.get_by_id(a.get("practice_link_id")) if a.get("practice_link_id") else None
    student_url = (request.url_root.rstrip("/") + url_for("public_practice", token=practice_link["token"])) if practice_link else None
    # Calculate average score
    avg = 0
    submissions = status.get("submissions") or []
    if submissions:
        avg = sum(s.get("percentage") or 0 for s in submissions) / len(submissions)
    return render_template("assignment_detail.html", assignment=a, classroom=cls, topic=topic, submitted=status["submitted"], not_submitted=status["not_submitted"], total_students=status["total"], submitted_count=len(status["submitted"]), not_submitted_count=len(status["not_submitted"]), avg_score=avg, practice_link=practice_link, student_url=student_url)


# ==============================================================================
# AI & Generate
# ==============================================================================
@app.route("/ai-slides", methods=["GET", "POST"])
@login_required
def ai_slides():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Topic title required.", "error")
            return render_template("ai_slides_form.html")
        bundle = generate_lesson_bundle(title=title, level=request.form.get("level", "Secondary"), language=request.form.get("language", "EN"), style=request.form.get("style", "Minimal"), text_model="gpt-4o-mini")
        slides = bundle.get("slides", []) or []
        topic = Topic.create(session["user_id"], title, f"AI generated", json.dumps({"slides": slides}, ensure_ascii=False), "ai", None)
        _save_game_and_practice(topic["id"], bundle.get("game") or {}, bundle.get("practice") or [])
        return redirect(url_for("topic_detail", topic_id=topic["id"]))
    return render_template("ai_slides_form.html")

def _extract_text_from_pdf(path):
    from pypdf import PdfReader
    return "\n\n".join(p.extract_text() or "" for p in PdfReader(path).pages).strip()

def _save_game_only(topic_id, game):
    GameQuestion.delete_by_topic(topic_id)
    for set_no in [1, 2, 3]:
        for tile_no, it in enumerate((game.get(str(set_no)) or [])[:24], 1):
            q, a = (it.get("question") or "").strip(), (it.get("answer") or "").strip()
            if q and a: GameQuestion.create(topic_id, set_no, tile_no, q, a, int(it.get("points") or 10))

def _save_practice_only(topic_id, practice):
    PracticeQuestion.delete_by_topic(topic_id)
    for it in (practice or []):
        prompt, choices = (it.get("question") or "").strip(), it.get("choices") or []
        if not prompt or len(choices) != 4: continue
        ci = max(0, min(int(it.get("correct_index") or 0), 3))
        PracticeQuestion.create(topic_id, "multiple_choice", json.dumps({"prompt": prompt, "choices": choices}), str(choices[ci]).strip())

def _save_game_and_practice(topic_id, game, practice):
    _save_game_only(topic_id, game)
    _save_practice_only(topic_id, practice)

@app.route("/api/topic/<int:topic_id>/generate", methods=["POST"])
@login_required
def api_generate_from_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)
    if not topic.get("pdf_file"): return _json_error("No PDF", 400)
    mode = ((request.get_json(silent=True) or {}).get("mode") or "all").lower()
    path = os.path.join(app.config["UPLOAD_FOLDER"], topic["pdf_file"])
    if not os.path.exists(path): return _json_error("PDF not found", 404)
    try: text = _extract_text_from_pdf(path)
    except Exception as e: return _json_error(str(e), 400)
    try: bundle = generate_lesson_bundle(f"{topic['name']}\n\n[PDF]\n{text[:8000]}", "Secondary", "EN", "Minimal", "gpt-4o-mini")
    except Exception as e: return _json_error(str(e), 500)
    if mode == "game": _save_game_only(topic_id, bundle.get("game") or {})
    elif mode == "practice": _save_practice_only(topic_id, bundle.get("practice") or [])
    else: _save_game_and_practice(topic_id, bundle.get("game") or {}, bundle.get("practice") or [])
    return jsonify({"ok": True})


# ==============================================================================
# Admin
# ==============================================================================
@app.route("/admin")
@admin_required
def admin_dashboard(): return render_template("admin_dashboard.html", topics=Topic.get_all())

@app.route("/admin/topics/create", methods=["GET", "POST"])
@admin_required
def admin_create_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name: flash("Name required.", "error"); return render_template("admin_create_topic.html")
        topic = Topic.create(session["user_id"], name, request.form.get("description") or "", json.dumps({"slides": []}), "manual", None)
        return redirect(url_for("admin_edit_topic", topic_id=topic["id"]))
    return render_template("admin_create_topic.html")

@app.route("/admin/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_topic(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic: return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slides_json = request.form.get("slides_json") or ""
        try: json.loads(slides_json)
        except: flash("Invalid JSON.", "error"); return render_template("admin_edit_topic.html", topic=topic)
        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename and allowed_file(file.filename):
            fn = f"topic{topic_id}_{secrets.token_hex(6)}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            pdf_filename = fn
        Topic.update(topic_id, name, request.form.get("description") or "", slides_json, pdf_filename)
        flash("Saved.", "success")
    return render_template("admin_edit_topic.html", topic=Topic.get_by_id(topic_id))

@app.route("/admin/topics/<int:topic_id>/delete", methods=["POST"])
@admin_required
def admin_delete_topic(topic_id):
    Topic.delete(topic_id)
    return redirect(url_for("admin_dashboard"))


# ==============================================================================
# Errors
# ==============================================================================
@app.errorhandler(403)
def forbidden(e): return (jsonify({"ok": False, "error": "Forbidden"}), 403) if _wants_json_response() else (render_template("error.html", error_code=403, error_msg="ไม่มีสิทธิ์"), 403)
@app.errorhandler(404)
def not_found(e): return (jsonify({"ok": False, "error": "Not found"}), 404) if _wants_json_response() else (render_template("error.html", error_code=404, error_msg="ไม่พบหน้านี้"), 404)
@app.errorhandler(500)
def server_error(e): return (jsonify({"ok": False, "error": "Server error"}), 500) if _wants_json_response() else (render_template("error.html", error_code=500, error_msg="เกิดข้อผิดพลาด"), 500)

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") == "development", host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
