import os
import json
import secrets
from io import BytesIO
from datetime import datetime
from typing import Optional

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort, jsonify, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit

from models import (
    init_db, get_db,
    User, Topic,
    GameQuestion, PracticeQuestion,
    AttemptHistory,
    PracticeLink, PracticeSubmission
)

from ai_generator import generate_lesson_bundle

# ------------------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ------------------------------------------------------------------------------
# DB init
# ------------------------------------------------------------------------------
init_db()

# ------------------------------------------------------------------------------
# Plans / Limits
# ------------------------------------------------------------------------------
FREE_TOPIC_LIMIT = 5  # ✅ free ได้สูงสุด 5 topics

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _current_user() -> Optional[dict]:
    uid = session.get("user_id")
    if not uid:
        return None
    return User.get_by_id(uid)

def _current_plan(user: Optional[dict]) -> str:
    if not user:
        return "free"
    if user.get("role") == "admin":
        return "admin"
    return (user.get("plan") or "free").strip().lower()

def _topic_limit_for_user(user: dict) -> Optional[int]:
    # admin / pro ไม่จำกัด
    plan = _current_plan(user)
    if plan in ("admin", "pro"):
        return None
    return FREE_TOPIC_LIMIT

def _topic_count_for_user(user_id: int) -> int:
    # models.py มี Topic.get_by_owner อยู่แล้ว
    rows = Topic.get_by_owner(user_id)
    return len(rows or [])

def _can_create_topic(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    limit = _topic_limit_for_user(user)
    if limit is None:
        return True
    return _topic_count_for_user(user["id"]) < limit

def _plan_badge_text(user: Optional[dict]) -> str:
    plan = _current_plan(user)
    if plan == "admin":
        return "ADMIN"
    if plan == "pro":
        return "PRO 69฿"
    return "FREE"

def _enforce_can_create_or_redirect() -> Optional[any]:
    """
    ✅ บังคับฝั่ง backend: ถ้า FREE ครบ limit แล้ว ห้ามเข้า create/ai-slides
    คืนค่า redirect response ถ้าถูกบล็อก, ถ้าไม่ถูกบล็อกคืน None
    """
    user = _current_user()
    if not user:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    if _can_create_topic(user):
        return None

    limit = _topic_limit_for_user(user) or FREE_TOPIC_LIMIT
    my_count = _topic_count_for_user(user["id"])
    flash(f"Free plan จำกัด {limit} เนื้อหา (ตอนนี้มี {my_count} แล้ว) — กรุณาอัปเกรดเพื่อสร้างเพิ่ม", "error")
    return redirect(url_for("pricing"))

# ------------------------------------------------------------------------------
# Auth decorators
# ------------------------------------------------------------------------------
from functools import wraps

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

def _is_admin() -> bool:
    return session.get("role") == "admin"

def _can_access_topic(topic: dict) -> bool:
    if _is_admin():
        return True
    return int(topic.get("owner_id") or 0) == int(session.get("user_id") or 0)

def _get_topic_or_404(topic_id: int) -> dict:
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)
    if not _can_access_topic(topic):
        abort(403)
    return topic

# ------------------------------------------------------------------------------
# Landing & Auth
# ------------------------------------------------------------------------------
@app.route("/")
def landing():
    return render_template("landing.html")

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
        flash("Registration successful! Please log in.", "success")
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
            session["plan"] = (user.get("plan") or "free")
            flash(f"Welcome back, {email}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("landing"))

# ------------------------------------------------------------------------------
# Pricing / Billing (MVP simulation)
# ------------------------------------------------------------------------------
@app.route("/pricing")
@login_required
def pricing():
    user = _current_user()
    return render_template(
        "pricing.html",
        user=user,
        plan=_current_plan(user),
        plan_badge=_plan_badge_text(user)
    )

@app.route("/billing/upgrade-pro", methods=["POST"])
@login_required
def upgrade_pro():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))

    # ✅ ใช้เมธอดที่มีจริงใน models.py (โปรเจกต์คุณก่อนหน้านี้ใช้ set_plan)
    if hasattr(User, "set_plan"):
        User.set_plan(user["id"], "pro")
    elif hasattr(User, "update_plan"):
        User.update_plan(user["id"], "pro")
    else:
        flash("User plan update method not found in models.py", "error")
        return redirect(url_for("pricing"))

    session["plan"] = "pro"
    flash("อัปเกรดเป็น PRO แล้ว ✅", "success")
    return redirect(url_for("dashboard"))

@app.route("/billing/downgrade-free", methods=["POST"])
@login_required
def downgrade_free():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))

    if hasattr(User, "set_plan"):
        User.set_plan(user["id"], "free")
    elif hasattr(User, "update_plan"):
        User.update_plan(user["id"], "free")
    else:
        flash("User plan update method not found in models.py", "error")
        return redirect(url_for("pricing"))

    session["plan"] = "free"
    flash("ดาวน์เกรดเป็น FREE แล้ว ✅", "success")
    return redirect(url_for("dashboard"))

# ------------------------------------------------------------------------------
# Serve uploads (PDF) - login required
# ------------------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ------------------------------------------------------------------------------
# Dashboard / Topics
# ------------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user = _current_user()
    user_id = session["user_id"]

    my_topics = Topic.get_by_owner(user_id)
    topics = Topic.get_all() if _is_admin() else my_topics
    recent = AttemptHistory.get_recent_by_user(user_id, limit=5)

    plan = _current_plan(user)
    can_create = _can_create_topic(user)
    free_limit = _topic_limit_for_user(user) or FREE_TOPIC_LIMIT
    my_count = _topic_count_for_user(user_id)

    return render_template(
        "dashboard.html",
        my_topics=my_topics,
        topics=topics,
        recent=recent,
        can_create=can_create,
        free_limit=free_limit,
        my_count=my_count,
        plan=plan,
    )

@app.route("/topic/<int:topic_id>")
@login_required
def topic_detail(topic_id):
    topic = _get_topic_or_404(topic_id)
    AttemptHistory.track_view(session["user_id"], topic_id)

    is_owner = int(topic.get("owner_id") or 0) == int(session["user_id"])
    return render_template("topic_detail.html", topic=topic, is_owner=is_owner, is_admin=_is_admin())

# ------------------------------------------------------------------------------
# My Topics CRUD
# ------------------------------------------------------------------------------
@app.route("/my/topics/create", methods=["GET", "POST"])
@login_required
def my_create_topic():
    # ✅ บล็อก backend
    blocked = _enforce_can_create_or_redirect()
    if blocked:
        return blocked

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=None, mode="create")

        slides_json = json.dumps({"slides": []}, ensure_ascii=False)
        topic = Topic.create(
            owner_id=session["user_id"],
            name=name,
            description=description,
            slides_json=slides_json,
            topic_type="manual",
            pdf_file=None,
        )
        flash("Created topic successfully.", "success")
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

        try:
            json.loads(slides_json)
        except Exception:
            flash("Invalid JSON in slides.", "error")
            return render_template("my_topic_edit.html", topic=topic, mode="edit")

        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Only PDF files are allowed.", "error")
                return render_template("my_topic_edit.html", topic=topic, mode="edit")

            safe_name = secure_filename(file.filename)
            token = secrets.token_hex(6)
            final_name = f"user{session['user_id']}_topic{topic_id}_{token}_{safe_name}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], final_name)
            file.save(save_path)
            pdf_filename = final_name

        Topic.update(topic_id, name, description, slides_json, pdf_filename)
        flash("Saved changes.", "success")
        return redirect(url_for("topic_detail", topic_id=topic_id))

    return render_template("my_topic_edit.html", topic=topic, mode="edit")

@app.route("/my/topics/<int:topic_id>/delete", methods=["POST"])
@login_required
def my_delete_topic(topic_id):
    _ = _get_topic_or_404(topic_id)
    Topic.delete(topic_id)
    flash("Deleted topic.", "success")
    return redirect(url_for("dashboard"))

# ------------------------------------------------------------------------------
# Slides
# ------------------------------------------------------------------------------
@app.route("/topic/<int:topic_id>/slides")
@login_required
def view_slides(topic_id):
    topic = _get_topic_or_404(topic_id)

    if topic.get("pdf_file"):
        pdf_url = url_for("uploaded_file", filename=topic["pdf_file"])
        return render_template("slides_pdf_presentation.html", topic=topic, pdf_url=pdf_url)

    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except Exception:
            slides = []

    return render_template("slides_viewer.html", topic=topic, slides=slides)

# ------------------------------------------------------------------------------
# Game (Bamboozle)
# ------------------------------------------------------------------------------
@app.route("/topic/<int:topic_id>/game")
@login_required
def game(topic_id):
    topic = _get_topic_or_404(topic_id)
    return render_template("game.html", topic=topic)

@app.route("/api/game/<int:topic_id>/sets")
@login_required
def api_game_sets(topic_id):
    _ = _get_topic_or_404(topic_id)

    sets_data = {}
    for set_no in range(1, 4):
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            tiles = [
                {"id": q["id"], "question": q["question"], "answer": q["answer"], "points": q["points"]}
                for q in questions
            ]
            sets_data[str(set_no)] = tiles

    return jsonify(sets_data)

# ------------------------------------------------------------------------------
# Practice helpers
# ------------------------------------------------------------------------------
def _normalize_practice_questions(rows):
    out = []
    for r in rows:
        q = dict(r)
        prompt = ""
        choices = []
        raw = q.get("question") or ""
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                prompt = (obj.get("prompt") or "").strip()
                ch = obj.get("choices") or []
                if isinstance(ch, list):
                    choices = [str(x) for x in ch]
            else:
                prompt = str(obj)
        except Exception:
            prompt = str(raw)

        out.append({
            "id": q.get("id"),
            "prompt": prompt,
            "choices": choices,
            "correct_answer": q.get("correct_answer") or "",
        })
    return out

def _build_practice_pdf(topic_title: str, questions, include_answers: bool = False) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    margin_x = 2 * cm
    y = height - 2 * cm
    line_h = 14
    max_w = width - (2 * margin_x)

    def draw_lines(lines, y0):
        y = y0
        for ln in lines:
            if y < 2 * cm:
                c.showPage()
                y = height - 2 * cm
            c.drawString(margin_x, y, ln)
            y -= line_h
        return y

    c.setFont("Helvetica-Bold", 16)
    y = draw_lines([f"Practice Worksheet: {topic_title}"], y)
    c.setFont("Helvetica", 11)
    y = draw_lines(["Name: ________________________   Class: __________   No.: ________", ""], y)

    for i, q in enumerate(questions, start=1):
        prompt = q.get("prompt") or ""
        choices = q.get("choices") or []

        c.setFont("Helvetica-Bold", 12)
        wrapped_q = simpleSplit(f"{i}. {prompt}", "Helvetica-Bold", 12, max_w)
        y = draw_lines(wrapped_q, y)

        c.setFont("Helvetica", 11)
        if choices and len(choices) == 4:
            labels = ["A", "B", "C", "D"]
            for lab, ch in zip(labels, choices):
                wrapped_c = simpleSplit(f"   ({lab}) {ch}", "Helvetica", 11, max_w)
                y = draw_lines(wrapped_c, y)
        else:
            y = draw_lines(["   _______________________________"], y)

        if include_answers:
            ans = q.get("correct_answer") or ""
            y = draw_lines([f"   Answer: {ans}"], y)

        y = draw_lines([""], y)

    c.showPage()
    c.save()
    return buf.getvalue()

# ------------------------------------------------------------------------------
# Practice (Teacher view)
# ------------------------------------------------------------------------------
@app.route("/topic/<int:topic_id>/practice")
@login_required
def practice(topic_id):
    topic = _get_topic_or_404(topic_id)

    rows = PracticeQuestion.get_by_topic(topic_id)
    questions = _normalize_practice_questions(rows)

    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    student_url = None
    if link:
        student_url = request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])

    return render_template("practice.html", topic=topic, questions=questions, student_url=student_url)

@app.route("/api/practice/<int:topic_id>/submit", methods=["POST"])
@login_required
def api_practice_submit(topic_id):
    _ = _get_topic_or_404(topic_id)

    data = request.get_json() or {}
    answers = data.get("answers", {})

    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    score = 0
    total = len(questions)
    feedback = {}

    for q in questions:
        q_id = str(q["id"])
        user_answer = (answers.get(q_id, "") or "").strip().lower()
        correct_answer = (q.get("correct_answer") or "").strip().lower()

        is_correct = user_answer == correct_answer
        if is_correct:
            score += 1

        feedback[q_id] = {
            "is_correct": is_correct,
            "user_answer": answers.get(q_id, ""),
            "correct_answer": q.get("correct_answer"),
        }

    percentage = (score / total * 100) if total > 0 else 0
    AttemptHistory.create(session["user_id"], topic_id, score, total, percentage)
    return jsonify({"score": score, "total": total, "percentage": percentage, "feedback": feedback})

@app.route("/api/practice/<int:topic_id>/link", methods=["POST"])
@login_required
def api_practice_create_link(topic_id):
    _ = _get_topic_or_404(topic_id)

    old = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    if old:
        PracticeLink.deactivate(old["id"])

    token = secrets.token_urlsafe(12)
    link = PracticeLink.create(topic_id, session["user_id"], token)
    student_url = request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])
    return jsonify({"url": student_url})

@app.route("/topic/<int:topic_id>/practice/pdf")
@login_required
def practice_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)

    include_answers = (request.args.get("answers") == "1")
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    pdf_bytes = _build_practice_pdf(topic["name"], questions, include_answers=include_answers)

    filename = f"practice_topic{topic_id}{'_answers' if include_answers else ''}.pdf"
    return (
        pdf_bytes,
        200,
        {
            "Content-Type": "application/pdf",
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )

# ------------------------------------------------------------------------------
# Public practice link (no login)
# ------------------------------------------------------------------------------
@app.route("/p/<token>")
def public_practice(token):
    link = PracticeLink.get_by_token(token)
    if not link or int(link.get("is_active") or 0) != 1:
        return render_template("error.html", error_code=404, error_msg="ลิงก์แบบฝึกหัดนี้ใช้ไม่ได้หรือหมดอายุ"), 404

    topic = Topic.get_by_id(link["topic_id"])
    if not topic:
        return render_template("error.html", error_code=404, error_msg="Topic not found"), 404

    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic["id"]))
    return render_template("practice_public.html", topic=topic, questions=questions, token=token)

@app.route("/api/p/<token>/submit", methods=["POST"])
def api_public_practice_submit(token):
    link = PracticeLink.get_by_token(token)
    if not link or int(link.get("is_active") or 0) != 1:
        return jsonify({"error": "Invalid link"}), 404

    data = request.get_json() or {}
    student_name = (data.get("student_name") or "").strip()
    answers = data.get("answers", {})
    if not student_name:
        return jsonify({"error": "student_name required"}), 400

    topic_id = link["topic_id"]
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))

    score = 0
    total = len(questions)
    feedback = {}

    for q in questions:
        q_id = str(q["id"])
        user_answer = (answers.get(q_id, "") or "").strip().lower()
        correct_answer = (q.get("correct_answer") or "").strip().lower()
        is_correct = (user_answer == correct_answer)
        if is_correct:
            score += 1
        feedback[q_id] = {
            "is_correct": is_correct,
            "user_answer": answers.get(q_id, ""),
            "correct_answer": q.get("correct_answer"),
        }

    percentage = (score / total * 100) if total > 0 else 0
    PracticeSubmission.create(
        link_id=link["id"],
        student_name=student_name,
        answers_json=json.dumps({"answers": answers}, ensure_ascii=False),
        score=score,
        total=total,
        percentage=percentage,
    )

    return jsonify({"score": score, "total": total, "percentage": percentage, "feedback": feedback})

# ------------------------------------------------------------------------------
# AI Lesson Bundle Generator: slides + game + practice
# ------------------------------------------------------------------------------
@app.route("/ai-slides", methods=["GET", "POST"])
@login_required
def ai_slides():
    # ✅ บล็อก backend
    blocked = _enforce_can_create_or_redirect()
    if blocked:
        return blocked

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        level = request.form.get("level", "Secondary")
        language = request.form.get("language", "EN")
        style = request.form.get("style", "Minimal")

        if not title:
            flash("Topic title required.", "error")
            return render_template("ai_slides_form.html")

        bundle = generate_lesson_bundle(
            title=title,
            level=level,
            language=language,
            style=style,
            text_model="gpt-4.1-mini",
        )

        slides = bundle.get("slides", []) or []
        game_data = bundle.get("game", {}) or {}
        practice_data = bundle.get("practice", []) or []

        slides_json_str = json.dumps({"slides": slides}, ensure_ascii=False)

        topic = Topic.create(
            owner_id=session["user_id"],
            name=title,
            description=f"AI generated • Level: {level} • Lang: {language} • Style: {style}",
            slides_json=slides_json_str,
            topic_type="ai",
            pdf_file=None,
        )

        GameQuestion.delete_by_topic(topic["id"])
        for set_no in [1, 2, 3]:
            items = (game_data.get(str(set_no), []) or [])[:24]
            for tile_no, it in enumerate(items, start=1):
                q = (it.get("question") or "").strip()
                a = (it.get("answer") or "").strip()
                pts = int(it.get("points") or 10)
                if q and a:
                    GameQuestion.create(topic["id"], set_no, tile_no, q, a, pts)

        PracticeQuestion.delete_by_topic(topic["id"])
        for it in (practice_data or []):
            prompt = (it.get("question") or "").strip()
            choices = it.get("choices") or []
            if not prompt or not isinstance(choices, list) or len(choices) != 4:
                continue
            ci = int(it.get("correct_index") or 0)
            ci = max(0, min(ci, 3))
            correct_answer = str(choices[ci]).strip()
            payload = {"prompt": prompt, "choices": [str(c).strip() for c in choices]}
            PracticeQuestion.create(
                topic["id"],
                "multiple_choice",
                json.dumps(payload, ensure_ascii=False),
                correct_answer,
            )

        flash("Slides + Game + Practice generated!", "success")
        return redirect(url_for("topic_detail", topic_id=topic["id"]))

    return render_template("ai_slides_form.html")

# ------------------------------------------------------------------------------
# Admin panel (ของเดิมคุณมีอยู่แล้ว ใช้ต่อได้)
# ------------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    topics = Topic.get_all()
    return render_template("admin_dashboard.html", topics=topics)

# ------------------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", error_code=403, error_msg="คุณไม่มีสิทธิ์เข้าถึงหน้านี้ (Forbidden)"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", error_code=404, error_msg="หน้านี้ไม่พบ (Page not found)"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", error_code=500, error_msg="เกิดข้อผิดพลาด (Server error)"), 500

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_ENV") == "development",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )
