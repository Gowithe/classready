# app.py
import os
import json
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from models import (
    init_db, get_db,
    User, Topic,
    GameQuestion, PracticeQuestion,
    PracticeLink, PracticeSubmission,
    AttemptHistory
)

from ai_generator import generate_lesson_bundle


# =========================
# App Config
# =========================
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB


# =========================
# Helpers
# =========================
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        user = User.get_by_id(session["user_id"])
        if not user or user.get("role") != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def current_user():
    uid = session.get("user_id")
    return User.get_by_id(uid) if uid else None


def parse_practice_row(row: dict) -> dict:
    """
    DB row practice_questions:
      - question: JSON string {"prompt":"..","choices":[...]}
      - correct_answer: correct choice text
    Convert to template-friendly object:
      {id, prompt, choices, correct_answer}
    """
    qjson = {}
    try:
        qjson = json.loads(row.get("question") or "{}")
    except Exception:
        qjson = {}
    prompt = qjson.get("prompt") or ""
    choices = qjson.get("choices") or []
    if not isinstance(choices, list):
        choices = []
    return {
        "id": row.get("id"),
        "prompt": prompt,
        "choices": choices,
        "correct_answer": row.get("correct_answer", "")
    }


def grade_answers(practice_rows: list, answers: dict):
    """
    practice_rows: list of parsed objects {id, prompt, choices, correct_answer}
    answers: {"<id>":"user answer text"}
    returns score, total, percentage, feedback dict
    """
    score = 0
    total = len(practice_rows)
    feedback = {}

    for q in practice_rows:
        qid = str(q["id"])
        user_ans = (answers.get(qid) or "").strip()
        correct = (q.get("correct_answer") or "").strip()
        is_correct = (user_ans == correct)

        if is_correct:
            score += 1

        feedback[qid] = {
            "is_correct": is_correct,
            "user_answer": user_ans,
            "correct_answer": correct
        }

    pct = (score / total * 100.0) if total else 0.0
    return score, total, pct, feedback


def topic_slides(topic: dict):
    """
    topic.slides_json: JSON string (list or dict)
    slides_viewer.html expects slides list
    """
    raw = topic.get("slides_json") or "[]"
    try:
        data = json.loads(raw)
    except Exception:
        data = []

    if isinstance(data, dict) and "slides" in data:
        data = data.get("slides") or []
    if not isinstance(data, list):
        data = []
    return data


# =========================
# Init DB
# =========================
with app.app_context():
    init_db()


# =========================
# Auth
# =========================
@app.get("/")
def landing():
    # ถ้าล็อกอินแล้วไป dashboard
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("landing.html") if os.path.exists(os.path.join(BASE_DIR, "templates", "landing.html")) else redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        if not email or not password:
            flash("Please fill email and password", "danger")
            return redirect(url_for("register"))

        if User.get_by_email(email):
            flash("Email already registered", "danger")
            return redirect(url_for("register"))

        # Default role = teacher
        user = User.create(email=email, password=password, role="teacher")
        session["user_id"] = user["id"]
        flash("Registered successfully ✅", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        user = User.get_by_email(email)
        if not user:
            flash("Invalid email or password", "danger")
            return redirect(url_for("login"))

        if not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password", "danger")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        flash("Welcome ✅", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("login"))


# =========================
# Dashboard / Topics
# =========================
@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    topics = Topic.get_all()
    recent = AttemptHistory.get_recent_by_user(user["id"]) if user else []
    return render_template("dashboard.html", user=user, topics=topics, recent=recent)


@app.get("/topic/<int:topic_id>")
@login_required
def topic_detail(topic_id):
    user = current_user()
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    # show pdf url if exists
    pdf_url = None
    if topic.get("pdf_file"):
        pdf_url = url_for("uploaded_file", filename=topic["pdf_file"])

    # show counts
    game_count = 0
    for set_no in (1, 2, 3):
        game_count += len(GameQuestion.get_by_topic_and_set(topic_id, set_no))
    practice_count = len(PracticeQuestion.get_by_topic(topic_id))

    return render_template(
        "topic_detail.html",
        user=user,
        topic=topic,
        pdf_url=pdf_url,
        game_count=game_count,
        practice_count=practice_count,
    )


@app.route("/admin/topic/new", methods=["GET", "POST"])
@admin_required
def admin_new_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        slides_json = request.form.get("slides_json") or "[]"
        topic_type = request.form.get("topic_type") or "manual"

        pdf_file = None
        f = request.files.get("pdf")
        if f and f.filename:
            if not allowed_file(f.filename):
                flash("Only PDF allowed", "danger")
                return redirect(url_for("admin_new_topic"))
            fn = secure_filename(f.filename)
            # unique
            fn = f"{secrets.token_hex(8)}_{fn}"
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            pdf_file = fn

        Topic.create(name=name, description=description, slides_json=slides_json, topic_type=topic_type, pdf_file=pdf_file)
        flash("Created topic ✅", "success")
        return redirect(url_for("dashboard"))

    return render_template("admin_topic_form.html") if os.path.exists(os.path.join(BASE_DIR, "templates", "admin_topic_form.html")) else abort(404)


@app.route("/admin/topic/<int:topic_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_topic(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        slides_json = request.form.get("slides_json") or (topic.get("slides_json") or "[]")

        pdf_file = topic.get("pdf_file")
        f = request.files.get("pdf")
        if f and f.filename:
            if not allowed_file(f.filename):
                flash("Only PDF allowed", "danger")
                return redirect(url_for("admin_edit_topic", topic_id=topic_id))
            fn = secure_filename(f.filename)
            fn = f"{secrets.token_hex(8)}_{fn}"
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            pdf_file = fn

        Topic.update(topic_id=topic_id, name=name, description=description, slides_json=slides_json, pdf_file=pdf_file)
        flash("Updated ✅", "success")
        return redirect(url_for("topic_detail", topic_id=topic_id))

    return render_template("admin_topic_form.html", topic=topic) if os.path.exists(os.path.join(BASE_DIR, "templates", "admin_topic_form.html")) else abort(404)


@app.post("/admin/topic/<int:topic_id>/delete")
@admin_required
def admin_delete_topic(topic_id):
    Topic.delete(topic_id)
    flash("Deleted ✅", "success")
    return redirect(url_for("dashboard"))


# =========================
# Upload Serving
# =========================
@app.get("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    # ครูดูไฟล์ได้หลัง login
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# =========================
# Slides
# =========================
@app.get("/topic/<int:topic_id>/slides")
@login_required
def slides(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    slides_list = topic_slides(topic)
    return render_template("slides_viewer.html", topic=topic, slides=slides_list)


@app.get("/topic/<int:topic_id>/presentation")
@login_required
def pdf_presentation(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    if not topic.get("pdf_file"):
        flash("No PDF uploaded for this topic", "danger")
        return redirect(url_for("topic_detail", topic_id=topic_id))

    pdf_url = url_for("uploaded_file", filename=topic["pdf_file"])
    return render_template("slides_pdf_presentation.html", topic=topic, pdf_url=pdf_url)

@app.get("/pricing")
def pricing():
    return """
    <html><head><title>Pricing</title></head>
    <body style="font-family:system-ui;padding:30px;">
      <h1>Pricing</h1>
      <p>Coming soon.</p>
      <p><a href="/dashboard">Back to Dashboard</a></p>
    </body></html>
    """


# =========================
# Game
# =========================
@app.get("/topic/<int:topic_id>/game")
@login_required
def game(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    set_no = int(request.args.get("set", "1") or "1")
    if set_no not in (1, 2, 3):
        set_no = 1

    questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)

    # ensure 24 tiles
    questions = (questions or [])[:24]
    while len(questions) < 24:
        questions.append({
            "id": 0,
            "topic_id": topic_id,
            "set_no": set_no,
            "tile_no": len(questions) + 1,
            "question": f"Bonus Q{len(questions)+1}",
            "answer": "Any reasonable answer",
            "points": 10,
        })

    return render_template("game.html", topic=topic, set_no=set_no, questions=questions)


# =========================
# Practice (Teacher view)
# =========================
@app.get("/topic/<int:topic_id>/practice")
@login_required
def practice(topic_id):
    user = current_user()
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    rows = PracticeQuestion.get_by_topic(topic_id)
    questions = [parse_practice_row(r) for r in rows]

    # latest active student link (if any)
    student_url = None
    if user:
        link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, user["id"])
        if link:
            student_url = url_for("public_practice", token=link["token"], _external=True)

    return render_template("practice.html", topic=topic, questions=questions, student_url=student_url)


# =========================
# Practice - Public Student Link
# =========================
@app.get("/p/<token>")
def public_practice(token):
    link = PracticeLink.get_by_token(token)
    if not link or link.get("is_active") != 1:
        return "This link is inactive.", 404

    topic = Topic.get_by_id(link["topic_id"])
    if not topic:
        return "Topic not found.", 404

    rows = PracticeQuestion.get_by_topic(topic["id"])
    questions = [parse_practice_row(r) for r in rows]
    return render_template("practice_public.html", topic=topic, questions=questions, token=token)


# =========================
# API: Create student link
# =========================
@app.post("/api/practice/<int:topic_id>/link")
@login_required
def api_create_practice_link(topic_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    topic = Topic.get_by_id(topic_id)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    # deactivate existing active link (optional)
    prev = PracticeLink.get_latest_active_by_topic_and_user(topic_id, user["id"])
    if prev:
        PracticeLink.deactivate(prev["id"])

    token = secrets.token_urlsafe(16)
    link = PracticeLink.create(topic_id=topic_id, created_by=user["id"], token=token)

    url = url_for("public_practice", token=link["token"], _external=True)
    return jsonify({"url": url})


# =========================
# API: Submit practice (teacher view)
# =========================
@app.post("/api/practice/<int:topic_id>/submit")
@login_required
def api_submit_practice(topic_id):
    user = current_user()
    topic = Topic.get_by_id(topic_id)
    if not user or not topic:
        return jsonify({"error": "Not found"}), 404

    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers") or {}
    if not isinstance(answers, dict):
        answers = {}

    rows = PracticeQuestion.get_by_topic(topic_id)
    parsed = [parse_practice_row(r) for r in rows]

    score, total, pct, feedback = grade_answers(parsed, answers)

    # track history
    AttemptHistory.create(user_id=user["id"], topic_id=topic_id, score=score, total=total, percentage=pct)

    return jsonify({
        "score": score,
        "total": total,
        "percentage": pct,
        "feedback": feedback
    })


# =========================
# API: Submit practice (public students)
# =========================
@app.post("/api/p/<token>/submit")
def api_submit_public_practice(token):
    link = PracticeLink.get_by_token(token)
    if not link or link.get("is_active") != 1:
        return jsonify({"error": "Invalid link"}), 404

    payload = request.get_json(silent=True) or {}
    student_name = (payload.get("student_name") or "").strip()
    answers = payload.get("answers") or {}
    if not student_name:
        return jsonify({"error": "Student name required"}), 400
    if not isinstance(answers, dict):
        answers = {}

    topic_id = link["topic_id"]
    rows = PracticeQuestion.get_by_topic(topic_id)
    parsed = [parse_practice_row(r) for r in rows]

    score, total, pct, feedback = grade_answers(parsed, answers)

    PracticeSubmission.create(
        link_id=link["id"],
        student_name=student_name,
        answers_json=json.dumps(answers, ensure_ascii=False),
        score=score,
        total=total,
        percentage=pct,
    )

    return jsonify({
        "score": score,
        "total": total,
        "percentage": pct,
        "feedback": feedback
    })


# =========================
# Practice Scores (Teacher)
# =========================
@app.get("/topic/<int:topic_id>/practice_scores")
@login_required
def practice_scores(topic_id):
    user = current_user()
    topic = Topic.get_by_id(topic_id)
    if not topic or not user:
        abort(404)

    # default: latest active link created by this user for this topic
    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, user["id"])
    link_id = None
    if request.args.get("link_id"):
        try:
            link_id = int(request.args.get("link_id"))
        except Exception:
            link_id = None

    if link_id:
        link = PracticeLink.get_by_id(link_id)

    submissions = []
    student_url = None
    if link:
        student_url = url_for("public_practice", token=link["token"], _external=True)
        submissions = PracticeSubmission.get_by_link(link["id"], limit=500)

    return render_template(
        "practice_scores.html",
        topic=topic,
        link=link,
        student_url=student_url,
        submissions=submissions
    )


# =========================
# PDF Export Practice
# =========================
@app.get("/topic/<int:topic_id>/practice.pdf")
@login_required
def practice_pdf(topic_id):
    """
    สร้าง PDF แบบฝึกหัดแบบง่าย (EN friendly)
    - ?answers=1 จะใส่เฉลย
    """
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)

    show_answers = (request.args.get("answers") == "1")

    rows = PracticeQuestion.get_by_topic(topic_id)
    questions = [parse_practice_row(r) for r in rows]

    # create PDF file in memory-like temp file
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm

    tmp_name = f"practice_{topic_id}_{secrets.token_hex(6)}.pdf"
    tmp_path = os.path.join(app.config["UPLOAD_FOLDER"], tmp_name)

    c = canvas.Canvas(tmp_path, pagesize=A4)
    width, height = A4

    x = 2 * cm
    y = height - 2 * cm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, f"Practice Worksheet: {topic.get('name','')}")
    y -= 1.0 * cm

    c.setFont("Helvetica", 11)
    if show_answers:
        c.drawString(x, y, "Answer key included")
    else:
        c.drawString(x, y, "Choose the best answer.")
    y -= 1.0 * cm

    for i, q in enumerate(questions, start=1):
        prompt = q.get("prompt", "")
        choices = q.get("choices", [])
        correct = q.get("correct_answer", "")

        # page break
        if y < 4 * cm:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 2 * cm

        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, f"{i}. {prompt}")
        y -= 0.7 * cm

        c.setFont("Helvetica", 11)
        labels = ["A", "B", "C", "D"]
        for j, ch in enumerate(choices[:4]):
            line = f"   {labels[j]}) {ch}"
            if show_answers and ch == correct:
                line += "  ✓"
            c.drawString(x, y, line)
            y -= 0.6 * cm

        y -= 0.3 * cm

    c.save()

    return send_from_directory(app.config["UPLOAD_FOLDER"], tmp_name, as_attachment=True, download_name=f"practice_topic_{topic_id}.pdf")


# =========================
# AI Generate: All / Game / Practice (Fix 500 here)
# =========================
def save_game_practice_from_bundle(topic_id: int, bundle: dict, replace: bool = True):
    """
    ✅ FIX จุดพัง: practice ต้องเก็บ question เป็น JSON และ correct_answer เป็น "ข้อความคำตอบจริง"
    """
    if replace:
        # clear old
        GameQuestion.delete_by_topic(topic_id)
        PracticeQuestion.delete_by_topic(topic_id)

    # ---- Game ----
    game = bundle.get("game") or {}
    for set_key in ("1", "2", "3"):
        tiles = game.get(set_key) or []
        set_no = int(set_key)

        # ensure 24
        tiles = tiles[:24]
        while len(tiles) < 24:
            tiles.append({"question": f"Bonus Q{len(tiles)+1}", "answer": "Any reasonable answer", "points": 10})

        for idx, t in enumerate(tiles, start=1):
            qtext = (t.get("question") or "").strip()
            ans = (t.get("answer") or "").strip()
            pts = int(t.get("points") or 10)
            if pts not in (10, 15, 20):
                pts = 10

            if not qtext:
                qtext = f"Q{idx}"
            if not ans:
                ans = "Any reasonable answer"

            GameQuestion.create(
                topic_id=topic_id,
                set_no=set_no,
                tile_no=idx,
                question=qtext,
                answer=ans,
                points=pts
            )

    # ---- Practice ----
    practice = bundle.get("practice") or []
    for p in practice:
        q = (p.get("question") or "").strip()
        choices = p.get("choices") or []
        ci = p.get("correct_index")

        if not q or not isinstance(choices, list) or len(choices) < 2:
            continue

        # normalize to 4 choices
        choices = [str(x).strip() for x in choices if str(x).strip()]
        while len(choices) < 4:
            choices.append(f"Option {len(choices)+1}")
        choices = choices[:4]

        try:
            ci = int(ci)
        except Exception:
            ci = 0
        if ci < 0 or ci > 3:
            ci = 0

        correct_answer = choices[ci]  # ✅ สำคัญ: เก็บเป็น "ข้อความคำตอบจริง"

        question_json = json.dumps({
            "prompt": q,
            "choices": choices
        }, ensure_ascii=False)

        PracticeQuestion.create(
            topic_id=topic_id,
            q_type="multiple_choice",
            question=question_json,      # ✅ JSON string
            correct_answer=correct_answer # ✅ text
        )


@app.post("/topic/<int:topic_id>/generate/all")
@login_required
def generate_all(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    try:
        bundle = generate_lesson_bundle(title=topic["name"], level="Secondary", language="EN+TH", style="Modern")
        # save slides too
        slides = bundle.get("slides") or []
        Topic.update(topic_id, topic["name"], topic.get("description") or "", json.dumps(slides, ensure_ascii=False), topic.get("pdf_file"))

        save_game_practice_from_bundle(topic_id, bundle, replace=True)
        return jsonify({"ok": True})
    except Exception as e:
        print("GEN ALL ERROR:", e)
        return jsonify({"error": str(e)}), 500


@app.post("/topic/<int:topic_id>/generate/game")
@login_required
def generate_game_only(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    try:
        bundle = generate_lesson_bundle(title=topic["name"], level="Secondary", language="EN+TH", style="Modern")
        # only game replace
        if bundle.get("game"):
            GameQuestion.delete_by_topic(topic_id)

            game = bundle.get("game") or {}
            for set_key in ("1", "2", "3"):
                tiles = (game.get(set_key) or [])[:24]
                while len(tiles) < 24:
                    tiles.append({"question": f"Bonus Q{len(tiles)+1}", "answer": "Any reasonable answer", "points": 10})

                for idx, t in enumerate(tiles, start=1):
                    GameQuestion.create(
                        topic_id=topic_id,
                        set_no=int(set_key),
                        tile_no=idx,
                        question=(t.get("question") or "").strip() or f"Q{idx}",
                        answer=(t.get("answer") or "").strip() or "Any reasonable answer",
                        points=int(t.get("points") or 10) if int(t.get("points") or 10) in (10, 15, 20) else 10
                    )

        return jsonify({"ok": True})
    except Exception as e:
        print("GEN GAME ERROR:", e)
        return jsonify({"error": str(e)}), 500


@app.post("/topic/<int:topic_id>/generate/practice")
@login_required
def generate_practice_only(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    try:
        bundle = generate_lesson_bundle(title=topic["name"], level="Secondary", language="EN+TH", style="Modern")
        # only practice replace (✅ fixed)
        PracticeQuestion.delete_by_topic(topic_id)

        practice = bundle.get("practice") or []
        for p in practice:
            q = (p.get("question") or "").strip()
            choices = p.get("choices") or []
            ci = p.get("correct_index")

            if not q or not isinstance(choices, list):
                continue

            choices = [str(x).strip() for x in choices if str(x).strip()]
            while len(choices) < 4:
                choices.append(f"Option {len(choices)+1}")
            choices = choices[:4]

            try:
                ci = int(ci)
            except Exception:
                ci = 0
            if ci < 0 or ci > 3:
                ci = 0

            correct_answer = choices[ci]  # ✅ FIX

            question_json = json.dumps({"prompt": q, "choices": choices}, ensure_ascii=False)

            PracticeQuestion.create(
                topic_id=topic_id,
                q_type="multiple_choice",
                question=question_json,
                correct_answer=correct_answer
            )

        return jsonify({"ok": True})
    except Exception as e:
        print("GEN PRACTICE ERROR:", e)
        return jsonify({"error": str(e)}), 500


# =========================
# Health
# =========================
@app.get("/healthz")
def healthz():
    return "ok", 200


# =========================
# Run (local)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
