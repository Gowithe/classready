# ==============================================================================
# FILE: app.py
# Teacher Platform MVP (Flask + SQLite)
# REFACTORED: Routes extracted to blueprints/ — this file keeps only:
#   dashboard, topic CRUD, slides, AI generation, error handlers
# ==============================================================================

import os
import json
import secrets
import base64
import textwrap
from urllib.parse import quote as url_quote
import tempfile
import threading
import uuid
from io import BytesIO
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort, Response,
)
from werkzeug.utils import secure_filename

from models import (
    get_db, init_db, User, Topic, GameQuestion, PracticeQuestion,
    AttemptHistory, Classroom, ClassroomStudent, Assignment,
    UserSubscription, UsageLimits,
)
from ai_generator import generate_lesson_bundle

from dotenv import load_dotenv
load_dotenv()

# --- Rate Limiting ---
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _limiter_available = True
except ImportError:
    _limiter_available = False
    print("\u26a0\ufe0f  flask-limiter not installed — API rate limiting disabled")
    print("   Install with: pip install Flask-Limiter")

# --- Shared helpers (used by both app.py and blueprints) ---
from blueprints.helpers import (
    login_required, admin_required,
    _is_admin, _can_access_topic, _get_topic_or_404,
    _wants_json_response, _json_error, is_premium_user,
)


# ==============================================================================
# App Init
# ==============================================================================
init_db()
app = Flask(__name__)

# Security: SECRET_KEY must be set via env var in production
_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    if os.environ.get("FLASK_ENV") == "development" or os.environ.get("RENDER") is None:
        _secret = "dev-only-" + secrets.token_hex(16)
        print("\u26a0\ufe0f  WARNING: SECRET_KEY not set — using random dev key (sessions reset on restart)")
    else:
        raise RuntimeError(
            "\u274c SECRET_KEY environment variable is required in production! "
            "Set it in Render Dashboard → Environment → SECRET_KEY"
        )
app.secret_key = _secret

# --- Initialize Rate Limiter ---
if _limiter_available:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],              # No global default — opt-in per route
        storage_uri="memory://",
    )
    print("\u2705 Rate limiting enabled")
else:
    limiter = None

# Make limiter accessible to blueprints via app config
app.config["LIMITER"] = limiter


def rate_limit(limit_string):
    """Decorator: apply rate limit if flask-limiter is available, otherwise no-op."""
    def decorator(f):
        if limiter:
            return limiter.limit(limit_string)(f)
        return f
    return decorator


# ==============================================================================
# Background Task Manager (avoids Cloudflare 524 timeout for AI generation)
# ==============================================================================
_tasks = {}  # task_id -> {status, result, error, created_at}
_tasks_lock = threading.Lock()


def _create_task():
    task_id = uuid.uuid4().hex[:12]
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.utcnow(),
        }
    return task_id


def _update_task(task_id, **kwargs):
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


def _get_task(task_id):
    with _tasks_lock:
        return _tasks.get(task_id, {}).copy()


def _cleanup_old_tasks():
    """Remove tasks older than 30 minutes."""
    cutoff = datetime.utcnow()
    with _tasks_lock:
        old = [k for k, v in _tasks.items()
               if (cutoff - v["created_at"]).total_seconds() > 1800]
        for k in old:
            del _tasks[k]

# Use persistent disk on Render, local folder otherwise
if os.path.isdir("/var/data"):
    UPLOAD_FOLDER = "/var/data/uploads"
    # Migrate: copy files from old location if any exist
    _old_uploads = os.path.join(os.path.dirname(__file__), "uploads")
    if os.path.isdir(_old_uploads):
        for _f in os.listdir(_old_uploads):
            _src = os.path.join(_old_uploads, _f)
            _dst = os.path.join(UPLOAD_FOLDER, _f)
            if os.path.isfile(_src) and not os.path.exists(_dst):
                import shutil
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                shutil.copy2(_src, _dst)
                print(f"  Migrated upload: {_f}")
else:
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
print(f"📁 UPLOAD_FOLDER = {UPLOAD_FOLDER}")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


# --- Create default admin user (only if not exists) ---
with app.app_context():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@teacherplatform.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if not admin_password:
        # Generate a random password for first-time setup
        admin_password = secrets.token_urlsafe(16)
        print(f"\u26a0\ufe0f  ADMIN_PASSWORD not set! Generated temporary password for {admin_email}:")
        print(f"   {admin_password}")
        print(f"   \u2192 Set ADMIN_PASSWORD env var and restart, or change via admin panel.")

    if not User.get_by_email(admin_email):
        User.create(admin_email, admin_password, "admin")
        print(f"\u2705 Admin user created: {admin_email}")
    else:
        # Admin exists — don't overwrite, just skip
        pass


# ==============================================================================
# Register Blueprints
# ==============================================================================
from blueprints.auth import auth_bp
from blueprints.classroom import classroom_bp
from blueprints.game import game_bp
from blueprints.practice import practice_bp
from blueprints.library import library_bp
from blueprints.payment import payment_bp
from blueprints.admin import admin_bp
from blueprints.student import student_bp

app.register_blueprint(auth_bp)
app.register_blueprint(classroom_bp)
app.register_blueprint(game_bp)
app.register_blueprint(practice_bp)
app.register_blueprint(library_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)

# --- Backfill join_code for existing classrooms ---
try:
    _conn = get_db()
    _c = _conn.cursor()
    _c.execute("SELECT id FROM classrooms WHERE join_code IS NULL OR join_code = ''")
    _rows = _c.fetchall()
    if _rows:
        import random, string
        for _r in _rows:
            _code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            _c.execute("UPDATE classrooms SET join_code = ? WHERE id = ?", (_code, _r[0]))
        _conn.commit()
        print(f"\u2705 Backfilled join_code for {len(_rows)} classrooms")
    _conn.close()
except Exception as _e:
    print(f"[join_code backfill] {_e}")

# --- Apply rate limits to sensitive blueprint endpoints ---
if limiter:
    # Auth: anti-brute-force
    limiter.limit("10/minute")(app.view_functions["auth.login"])
    limiter.limit("3/minute")(app.view_functions["auth.register"])
    limiter.limit("5/minute")(app.view_functions["auth.forgot_password"])
    limiter.limit("5/minute")(app.view_functions["auth.reset_password"])
    limiter.limit("5/minute")(app.view_functions["auth.resend_verification"])
    # Practice/Game API: prevent spam submissions
    limiter.limit("30/minute")(app.view_functions["practice.api_practice_submit"])
    limiter.limit("30/minute")(app.view_functions["practice.api_public_practice_submit"])
    limiter.limit("30/minute")(app.view_functions["practice.api_public_fill_blanks_submit"])
    limiter.limit("30/minute")(app.view_functions["practice.api_public_unscramble_submit"])
    # Payment: prevent duplicate transactions
    limiter.limit("10/minute")(app.view_functions["payment.payment_create"])
    limiter.limit("10/minute")(app.view_functions["payment.payment_verify"])


# ==============================================================================
# Context Processor – inject freemium data to all templates
# ==============================================================================
@app.context_processor
def inject_freemium_data():
    if "user_id" in session:
        try:
            user_id = session["user_id"]
            is_premium = is_premium_user(user_id)
            stats = UsageLimits.get_user_stats(user_id)
            return {
                "user_is_premium": is_premium,
                "usage_stats": stats,
                "free_limits": {
                    "topics": UsageLimits.FREE_TOPICS,
                    "classrooms": UsageLimits.FREE_CLASSROOMS,
                    "ai_generate": UsageLimits.FREE_AI_GENERATE_PER_MONTH,
                    "students_per_classroom": UsageLimits.FREE_STUDENTS_PER_CLASSROOM,
                },
            }
        except Exception as e:
            print(f"Context processor error: {e}")
    return {
        "user_is_premium": False,
        "usage_stats": {"topic_count": 0, "classroom_count": 0, "ai_generate_count": 0},
        "free_limits": {
            "topics": 5,
            "classrooms": 2,
            "ai_generate": 3,
            "students_per_classroom": 50,
        },
    }


# ==============================================================================
# Static File Serving
# ==============================================================================
@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


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

    # ========== Dashboard Statistics ==========
    stats = {
        "total_topics": len(my_topics),
        "total_classrooms": len(classrooms),
        "total_students": 0,
        "total_submissions": 0,
    }

    for c in classrooms:
        students = ClassroomStudent.get_by_classroom(c["id"])
        stats["total_students"] += len(students)

    # Classroom progress & submissions
    classroom_progress = []
    all_submissions = []

    for c in classrooms:
        students = ClassroomStudent.get_by_classroom(c["id"])
        assignments = Assignment.get_by_classroom(c["id"])

        total_students = len(students)
        submitted_count = 0

        for a in assignments:
            status = Assignment.get_submissions_status(a["id"])
            submitted_count += len(status.get("submitted", []))
            all_submissions.extend(status.get("submissions", []))

        total_possible = total_students * len(assignments) if assignments else 0
        percentage = int((submitted_count / total_possible * 100)) if total_possible > 0 else 0

        classroom_progress.append({
            "id": c["id"],
            "name": c["name"],
            "total": total_students,
            "submitted": submitted_count,
            "percentage": percentage,
        })

    stats["total_submissions"] = len(all_submissions)

    # ========== Alerts ==========
    alerts = []

    for c in classrooms:
        assignments = Assignment.get_by_classroom(c["id"])
        for a in assignments:
            status = Assignment.get_submissions_status(a["id"])
            not_submitted = status.get("not_submitted", [])

            if not_submitted:
                alerts.append({
                    "type": "warning",
                    "title": f"{len(not_submitted)} \u0e04\u0e19\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e2a\u0e48\u0e07\u0e07\u0e32\u0e19",
                    "message": f"\u0e07\u0e32\u0e19 '{a['title']}' \u0e2b\u0e49\u0e2d\u0e07 {c['name']}",
                })

            for sub in status.get("submissions", []):
                if sub.get("percentage", 100) < 50:
                    sname = sub.get("student_name", "\u0e19\u0e31\u0e01\u0e40\u0e23\u0e35\u0e22\u0e19")
                    spct = sub.get("percentage", 0)
                    alerts.append({
                        "type": "danger",
                        "title": f"{sname} \u0e04\u0e30\u0e41\u0e19\u0e19\u0e15\u0e48\u0e33",
                        "message": f"\u0e44\u0e14\u0e49 {spct:.0f}% \u0e43\u0e19\u0e07\u0e32\u0e19 '{a['title']}'",
                    })

    # ========== Top & Struggling Students ==========
    student_scores = {}

    for sub in all_submissions:
        name = sub.get("student_name", "").strip()
        if not name:
            continue
        if name not in student_scores:
            student_scores[name] = {"name": name, "classroom": sub.get("classroom", "-"), "scores": []}
        student_scores[name]["scores"].append(sub.get("percentage", 0))

    for name, data in student_scores.items():
        data["avg_score"] = int(sum(data["scores"]) / len(data["scores"])) if data["scores"] else 0

    sorted_students = sorted(student_scores.values(), key=lambda x: x["avg_score"], reverse=True)
    top_students = [s for s in sorted_students if s["avg_score"] >= 70][:5]
    struggling_students = [s for s in sorted_students if s["avg_score"] < 50][:5]

    return render_template(
        "dashboard.html",
        my_topics=my_topics,
        topics=all_topics,
        recent=recent,
        classrooms=classrooms,
        stats=stats,
        classroom_progress=classroom_progress,
        alerts=alerts[:20],
        top_students=top_students,
        struggling_students=struggling_students,
    )


# ==============================================================================
# Topic Detail
# ==============================================================================
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
        except Exception:
            pass
    return render_template(
        "topic_detail.html",
        topic=topic,
        is_owner=is_owner,
        is_admin=_is_admin(),
        has_game=has_game,
        has_practice=has_practice,
        has_slides=has_slides,
    )


# ==============================================================================
# My Topics CRUD
# ==============================================================================
@app.route("/my/topics/create", methods=["GET", "POST"])
@login_required
def my_create_topic():
    is_premium = is_premium_user(session["user_id"])
    can_create, msg = UsageLimits.can_create_topic(session["user_id"], is_premium)

    if request.method == "POST":
        if not can_create:
            flash(f"\u274c {msg} - \u0e2d\u0e31\u0e1b\u0e40\u0e01\u0e23\u0e14\u0e40\u0e1b\u0e47\u0e19 Premium \u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e2a\u0e23\u0e49\u0e32\u0e07\u0e44\u0e21\u0e48\u0e08\u0e33\u0e01\u0e31\u0e14!", "error")
            return redirect(url_for("payment.pricing"))

        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=None, mode="create", can_create=can_create, limit_msg=msg)

        topic = Topic.create(session["user_id"], name, description, json.dumps({"slides": []}, ensure_ascii=False), "manual", None)
        flash("\u2705 \u0e2a\u0e23\u0e49\u0e32\u0e07 Topic \u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08!", "success")
        return redirect(url_for("my_edit_topic", topic_id=topic["id"]))

    return render_template("my_topic_edit.html", topic=None, mode="create", can_create=can_create, limit_msg=msg)


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

    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except Exception:
            pass

    if slides:
        return render_template("slides_viewer.html", topic=topic, slides=slides)

    if topic.get("pdf_file"):
        return render_template(
            "slides_pdf_presentation.html",
            topic=topic,
            pdf_url=url_for("uploaded_file", filename=topic["pdf_file"]),
        )

    return render_template("slides_viewer.html", topic=topic, slides=[])


@app.route("/topic/<int:topic_id>/slides/edit")
@login_required
def edit_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    return render_template("slides_editor.html", topic=topic)


@app.route("/api/topic/<int:topic_id>/slides", methods=["POST"])
@login_required
@rate_limit("30/minute")
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
            except Exception:
                pass
        processed.append(ps)
    Topic.update(
        topic_id,
        topic["name"],
        topic["description"],
        json.dumps({"slides": processed}, ensure_ascii=False),
        topic.get("pdf_file"),
    )
    return jsonify({"ok": True})


# ==============================================================================
# Save Game Questions API (Mystery Tiles Editor)
# ==============================================================================
@app.route("/api/topic/<int:topic_id>/game-questions", methods=["POST"])
@login_required
def api_save_game_questions(topic_id):
    topic = _get_topic_or_404(topic_id)
    data = request.get_json(silent=True) or {}
    game = data.get("game") or {}
    if not game:
        return jsonify({"ok": False, "error": "No game data"}), 400
    try:
        _save_game_only(topic_id, game)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ==============================================================================
# Save Practice Questions API (Millionaire MCQ Editor)
# ==============================================================================
@app.route("/api/topic/<int:topic_id>/practice-questions", methods=["POST"])
@login_required
def api_save_practice_questions(topic_id):
    topic = _get_topic_or_404(topic_id)
    data = request.get_json(silent=True) or {}
    practice = data.get("practice") or []
    if not practice:
        return jsonify({"ok": False, "error": "No practice data"}), 400
    try:
        _save_practice_only(topic_id, practice)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ==============================================================================
# Save Vocabulary API (Memory Match Editor)
# ==============================================================================
@app.route("/api/topic/<int:topic_id>/vocabulary", methods=["POST"])
@login_required
def api_save_vocabulary(topic_id):
    topic = _get_topic_or_404(topic_id)
    data = request.get_json(silent=True) or {}
    vocabulary = data.get("vocabulary") or []
    if not isinstance(vocabulary, list):
        return jsonify({"ok": False, "error": "Invalid vocabulary data"}), 400
    try:
        slides_raw = topic.get("slides_json") or "{}"
        slides_obj = json.loads(slides_raw) if slides_raw else {}
        slides = slides_obj.get("slides", slides_obj) if isinstance(slides_obj, dict) else slides_obj
        if not isinstance(slides, list):
            slides = []

        vocab_slide_idx = None
        for i, slide in enumerate(slides):
            if isinstance(slide, dict) and slide.get("type") == "vocabulary":
                vocab_slide_idx = i
                break

        vocab_items = []
        for v in vocabulary:
            word = (v.get("word") or "").strip()
            meaning = (v.get("meaning") or "").strip()
            if word and meaning:
                vocab_items.append({"word": word, "meaning": meaning})

        if vocab_slide_idx is not None:
            slides[vocab_slide_idx]["vocabulary"] = vocab_items
        else:
            slides.insert(0, {
                "type": "vocabulary",
                "title": "Vocabulary",
                "vocabulary": vocab_items,
            })

        new_json = json.dumps({"slides": slides}, ensure_ascii=False)
        Topic.update(topic_id, topic["name"], topic.get("description") or "", new_json, topic.get("pdf_file"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ==============================================================================
# Download Slides as PDF
# ==============================================================================
@app.route("/topic/<int:topic_id>/slides/download")
@login_required
def download_slides_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)

    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except Exception:
            pass

    if not slides:
        flash("\u0e44\u0e21\u0e48\u0e21\u0e35\u0e2a\u0e44\u0e25\u0e14\u0e4c", "error")
        return redirect(url_for("topic_detail", topic_id=topic_id))

    try:
        pdf_bytes = _generate_slides_pdf(topic["name"], slides)
    except Exception as e:
        print(f"\u274c PDF generation error: {e}")
        import traceback
        traceback.print_exc()
        flash(f"\u0e2a\u0e23\u0e49\u0e32\u0e07 PDF \u0e44\u0e21\u0e48\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08: {e}", "error")
        return redirect(url_for("topic_detail", topic_id=topic_id))

    # ASCII-only filename for HTTP header safety
    safe_name = "".join(c for c in topic["name"] if c.isascii() and (c.isalnum() or c in " -_")).strip()[:50] or "slides"
    utf8_name = url_quote(topic["name"][:50] + "_slides.pdf")

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{safe_name}_slides.pdf\"; filename*=UTF-8''{utf8_name}"},
    )


@app.route("/topic/<int:topic_id>/pdf-present")
@login_required
def pdf_presentation(topic_id):
    topic = _get_topic_or_404(topic_id)
    if not topic.get("pdf_file"):
        flash("\u0e44\u0e21\u0e48\u0e21\u0e35\u0e44\u0e1f\u0e25\u0e4c PDF", "error")
        return redirect(url_for("topic_detail", topic_id=topic_id))
    return render_template(
        "slides_pdf_presentation.html",
        topic=topic,
        pdf_url=url_for("uploaded_file", filename=topic["pdf_file"]),
    )


def _generate_slides_pdf(title, slides):
    """Generate a PDF from slides data – supports all slide types + Thai language."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import urllib.request

    buf = BytesIO()
    page_size = landscape(A4)
    c = canvas.Canvas(buf, pagesize=page_size)
    w, h = page_size

    # Register Thai font
    thai_font = "Helvetica"
    thai_font_bold = "Helvetica-Bold"
    thai_font_italic = "Helvetica-Oblique"

    font_paths = [
        "C:/Windows/Fonts/THSarabunNew.ttf",
        "C:/Windows/Fonts/thsarabunnew.ttf",
        "C:/Windows/Fonts/Tahoma.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/cordia.ttf",
        "C:/Windows/Fonts/CordiaNew.ttf",
        "C:/Windows/Fonts/angsana.ttf",
        "/usr/share/fonts/truetype/thai/TH Sarabun New.ttf",
        "/usr/share/fonts/truetype/tlwg/TlwgTypo.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/Library/Fonts/Thonburi.ttf",
        "/System/Library/Fonts/Thonburi.ttc",
    ]

    font_bold_paths = [
        "C:/Windows/Fonts/THSarabunNew Bold.ttf",
        "C:/Windows/Fonts/thsarabunnew-bold.ttf",
        "C:/Windows/Fonts/tahomabd.ttf",
        "C:/Windows/Fonts/cordiab.ttf",
    ]

    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("ThaiFont", fp))
                thai_font = "ThaiFont"
                thai_font_italic = "ThaiFont"
                break
            except Exception:
                pass

    for fp in font_bold_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("ThaiFontBold", fp))
                thai_font_bold = "ThaiFontBold"
                break
            except Exception:
                pass

    custom_font_path = os.path.join(app.config["UPLOAD_FOLDER"], "THSarabunNew.ttf")
    if thai_font == "Helvetica" and os.path.exists(custom_font_path):
        try:
            pdfmetrics.registerFont(TTFont("ThaiFont", custom_font_path))
            thai_font = "ThaiFont"
            thai_font_italic = "ThaiFont"
        except Exception:
            pass

    # Colors
    primary_color = HexColor("#667eea")
    dark_color = HexColor("#1e293b")
    muted_color = HexColor("#64748b")
    bg_color = HexColor("#f8fafc")
    accent_color = HexColor("#10b981")

    base_size = 14 if thai_font != "Helvetica" else 12
    title_size = 24 if thai_font != "Helvetica" else 22

    def draw_bullet(x, y, text, max_width, font_size=None):
        if font_size is None:
            font_size = base_size
        if y < 2 * cm:
            return y
        c.setFillColor(primary_color)
        c.circle(x, y + 0.12 * cm, 0.1 * cm, fill=1, stroke=0)
        c.setFillColor(dark_color)
        c.setFont(thai_font, font_size)
        wrapped = textwrap.wrap(str(text), width=int(max_width / 6))
        for line in wrapped[:3]:
            c.drawString(x + 0.5 * cm, y, line)
            y -= 0.55 * cm
        return y - 0.15 * cm

    def extract_content_from_slide(slide):
        slide_type = slide.get("type", "")
        items = []

        content = slide.get("content", [])
        if isinstance(content, str):
            items.append(content)
        elif isinstance(content, list):
            for ct in content:
                if isinstance(ct, str):
                    items.append(ct)
                elif isinstance(ct, dict):
                    en = ct.get("en") or ct.get("text") or ""
                    th = ct.get("th") or ct.get("meaning") or ""
                    if en:
                        items.append(f"{en}" + (f" ({th})" if th else ""))

        objectives = slide.get("objectives", [])
        if isinstance(objectives, list):
            for obj in objectives:
                if isinstance(obj, str):
                    items.append(f"\u2022 {obj}")

        vocabulary = slide.get("vocabulary", []) or slide.get("items", [])
        if isinstance(vocabulary, list) and slide_type in ["vocabulary", ""]:
            for v in vocabulary[:8]:
                if isinstance(v, dict):
                    word = v.get("word", "")
                    meaning = v.get("meaning", "") or v.get("th", "")
                    example = v.get("example", "") or v.get("example_en", "")
                    if word:
                        line = f"\u2022 {word}"
                        if meaning:
                            line += f" - {meaning}"
                        items.append(line)
                        if example:
                            items.append(f"  Ex: {example}")

        examples = slide.get("examples", [])
        if isinstance(examples, list):
            for ex in examples[:6]:
                if isinstance(ex, dict):
                    en = ex.get("en", "")
                    th = ex.get("th", "")
                    if en:
                        items.append(f"\u2022 {en}" + (f" ({th})" if th else ""))
                elif isinstance(ex, str):
                    items.append(f"\u2022 {ex}")

        highlights = slide.get("highlights", [])
        if isinstance(highlights, list):
            for hl in highlights[:5]:
                if isinstance(hl, dict):
                    label = hl.get("label", "")
                    note = hl.get("note", "")
                    if label:
                        items.append(f"\u2022 {label}: {note}" if note else f"\u2022 {label}")

        pattern = slide.get("pattern") or slide.get("structure", "")
        if pattern and isinstance(pattern, str):
            items.insert(0, f"\U0001f50d {pattern}")

        prompt = slide.get("prompt", "")
        if prompt and isinstance(prompt, str):
            items.insert(0, prompt)

        keywords = slide.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            items.append(f"Keywords: {', '.join(str(k) for k in keywords)}")

        lines = slide.get("lines", [])
        if isinstance(lines, list):
            for line in lines[:8]:
                if isinstance(line, dict):
                    speaker = line.get("speaker", "")
                    text = line.get("en") or line.get("text", "")
                    if speaker and text:
                        items.append(f"{speaker}: {text}")
                elif isinstance(line, str):
                    items.append(line)

        scenario = slide.get("scenario", "")
        if scenario and isinstance(scenario, str):
            items.insert(0, f"\U0001f3ad {scenario}")

        practice_items = slide.get("items", [])
        if isinstance(practice_items, list) and slide_type == "guided_practice":
            for pi in practice_items[:4]:
                if isinstance(pi, dict):
                    q = pi.get("q") or pi.get("question", "")
                    if q:
                        items.append(f"Q: {q}")
                    choices = pi.get("choices", [])
                    if choices:
                        items.append(f"   A) {choices[0] if len(choices) > 0 else ''}")
                        items.append(f"   B) {choices[1] if len(choices) > 1 else ''}")
                        items.append(f"   C) {choices[2] if len(choices) > 2 else ''}")
                        items.append(f"   D) {choices[3] if len(choices) > 3 else ''}")

        mistakes = slide.get("common_mistakes", [])
        if isinstance(mistakes, list) and mistakes:
            items.append("")
            items.append("\u26a0\ufe0f Common mistakes:")
            for m in mistakes[:3]:
                items.append(f"  \u2022 {m}")

        bullets = slide.get("bullets", [])
        if isinstance(bullets, list):
            for b in bullets:
                if isinstance(b, str):
                    items.append(f"\u2022 {b}")

        return items

    for i, slide in enumerate(slides):
        slide_title = slide.get("title", f"Slide {i+1}")
        slide_type = slide.get("type", "")
        image_url = slide.get("image_url", "")

        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        c.setFillColor(primary_color)
        c.rect(0, h - 2.5 * cm, w, 2.5 * cm, fill=1, stroke=0)

        c.setFillColor(HexColor("#ffffff"))
        c.setFont("Helvetica", 10)
        c.drawRightString(w - 1 * cm, h - 1.5 * cm, f"{i+1} / {len(slides)}")

        if slide_type:
            c.setFont("Helvetica", 8)
            c.drawRightString(w - 1 * cm, h - 2 * cm, f"[{slide_type}]")

        c.setFillColor(HexColor("#ffffff"))
        c.setFont(thai_font_bold, title_size)
        display_title = slide_title[:55] + "..." if len(slide_title) > 55 else slide_title
        c.drawString(1.5 * cm, h - 1.7 * cm, display_title)

        y = h - 4 * cm
        content_width = w - 3 * cm

        img_x = None
        if image_url and not image_url.startswith("data:"):
            content_width = w * 0.55
            img_x = w * 0.58

        content_items = extract_content_from_slide(slide)

        c.setFillColor(dark_color)
        c.setFont(thai_font, base_size)

        for item in content_items:
            if y < 2 * cm:
                break

            item_str = str(item).strip()
            if not item_str:
                y -= 0.3 * cm
                continue

            if item_str.startswith("\u2022"):
                y = draw_bullet(1.5 * cm, y, item_str[1:].strip(), content_width, base_size)
            elif item_str.startswith("  \u2022"):
                y = draw_bullet(2.2 * cm, y, item_str[3:].strip(), content_width - 0.7 * cm, base_size - 1)
            elif item_str.startswith("\U0001f50d") or item_str.startswith("\U0001f3ad") or item_str.startswith("\u26a0\ufe0f"):
                c.setFont(thai_font_bold, base_size + 1)
                c.setFillColor(accent_color)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:2]:
                    c.drawString(1.5 * cm, y, line)
                    y -= 0.6 * cm
                c.setFillColor(dark_color)
                c.setFont(thai_font, base_size)
                y -= 0.2 * cm
            elif item_str.startswith("Q:"):
                c.setFont(thai_font_bold, base_size)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:2]:
                    c.drawString(1.5 * cm, y, line)
                    y -= 0.55 * cm
                c.setFont(thai_font, base_size)
            elif item_str.startswith("   "):
                c.setFont(thai_font, base_size - 1)
                c.drawString(2 * cm, y, item_str.strip())
                y -= 0.5 * cm
                c.setFont(thai_font, base_size)
            elif item_str.startswith("Ex:") or item_str.startswith("  Ex:"):
                c.setFont(thai_font_italic, base_size - 1)
                c.setFillColor(muted_color)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 6.5))
                for line in wrapped[:2]:
                    c.drawString(2 * cm, y, line)
                    y -= 0.5 * cm
                c.setFillColor(dark_color)
                c.setFont(thai_font, base_size)
            elif ":" in item_str and not item_str.startswith("Keywords"):
                parts = item_str.split(":", 1)
                c.setFont(thai_font_bold, base_size - 1)
                c.drawString(1.5 * cm, y, parts[0] + ":")
                c.setFont(thai_font, base_size - 1)
                if len(parts) > 1:
                    wrapped = textwrap.wrap(parts[1].strip(), width=int(content_width / 7))
                    first = True
                    for line in wrapped[:2]:
                        if first:
                            c.drawString(1.5 * cm + c.stringWidth(parts[0] + ": ", thai_font_bold, base_size - 1), y, line)
                            first = False
                        else:
                            c.drawString(2 * cm, y, line)
                        y -= 0.55 * cm
                else:
                    y -= 0.55 * cm
                c.setFont(thai_font, base_size)
            else:
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:3]:
                    c.drawString(1.5 * cm, y, line)
                    y -= 0.55 * cm
                y -= 0.1 * cm

        # Image
        if image_url and img_x:
            try:
                img_path = None

                if image_url.startswith("/uploads/"):
                    img_path = os.path.join(app.config["UPLOAD_FOLDER"], image_url.split("/uploads/")[-1])
                elif image_url.startswith("http"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        urllib.request.urlretrieve(image_url, tmp.name)
                        img_path = tmp.name

                if img_path and os.path.exists(img_path):
                    img_max_w = w * 0.38
                    img_max_h = h - 5 * cm

                    from reportlab.lib.utils import ImageReader

                    img = ImageReader(img_path)
                    iw, ih = img.getSize()

                    scale = min(img_max_w / iw, img_max_h / ih)
                    draw_w = iw * scale
                    draw_h = ih * scale

                    img_y = (h - 2.5 * cm - draw_h) / 2

                    c.drawImage(img_path, img_x, img_y, width=draw_w, height=draw_h, preserveAspectRatio=True)
            except Exception as e:
                print(f"Error loading image: {e}")

        # Footer
        c.setFillColor(muted_color)
        c.setFont(thai_font, 10)
        c.drawString(1.5 * cm, 0.8 * cm, title)

        c.showPage()

    c.save()
    return buf.getvalue()


# ==============================================================================
# AI Slides & PDF Generate (Background Task — avoids Cloudflare 524 timeout)
# ==============================================================================
@app.route("/ai-slides", methods=["GET", "POST"])
@login_required
def ai_slides():
    is_premium = is_premium_user(session["user_id"])
    can_create_topic, topic_msg = UsageLimits.can_create_topic(session["user_id"], is_premium)
    can_ai, ai_msg = UsageLimits.can_ai_generate(session["user_id"], is_premium)

    if request.method == "POST":
        # AJAX POST — return JSON immediately, run AI in background
        if not can_create_topic:
            return jsonify({"ok": False, "error": topic_msg, "upgrade_required": True}), 403
        if not can_ai:
            return jsonify({"ok": False, "error": ai_msg, "upgrade_required": True}), 403

        title = (request.form.get("title") or "").strip()
        if not title:
            return jsonify({"ok": False, "error": "Topic title required."}), 400

        level = request.form.get("level", "Secondary")
        language = request.form.get("language", "EN")
        style = request.form.get("style", "Minimal")
        user_id = session["user_id"]

        _cleanup_old_tasks()
        task_id = _create_task()

        def run_ai_generate():
            try:
                print(f"🟢 THREAD STARTED for task {task_id}")
                _update_task(task_id, status="generating")
                print(f"🟢 Calling generate_lesson_bundle(title={title}, lang={language})...")
                bundle = generate_lesson_bundle(
                    title=title, level=level, language=language,
                    style=style, text_model="gpt-4o-mini",
                )
                print(f"🟢 AI generation complete! slides={len(bundle.get('slides', []))}")
                slides = bundle.get("slides", []) or []

                with app.app_context():
                    print(f"🟢 Saving topic to DB...")
                    topic = Topic.create(
                        user_id, title, "AI generated",
                        json.dumps({"slides": slides}, ensure_ascii=False),
                        "ai", None,
                    )
                    print(f"🟢 Topic created: id={topic['id']}")
                    _save_game_and_practice(
                        topic["id"],
                        bundle.get("game") or {},
                        bundle.get("practice") or [],
                    )
                    UsageLimits.increment_ai_generate(user_id)
                    print(f"🟢 All saved! Marking task done.")

                _update_task(task_id, status="done", result={
                    "topic_id": topic["id"],
                    "redirect": f"/topic/{topic['id']}",
                })
            except Exception as e:
                import traceback
                print(f"🔴 THREAD ERROR: {e}")
                traceback.print_exc()
                _update_task(task_id, status="error", error=str(e))

        threading.Thread(target=run_ai_generate, daemon=True).start()
        return jsonify({"ok": True, "task_id": task_id})

    return render_template("ai_slides_form.html", can_ai=can_ai, ai_msg=ai_msg)


@app.route("/api/ai-task/<task_id>/status")
@login_required
def ai_task_status(task_id):
    """Poll endpoint — frontend checks every 3s until done/error."""
    task = _get_task(task_id)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({
        "ok": True,
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
    })


def _extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF (pypdf). Raises a friendly error if unreadable."""
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise Exception("Missing dependency: pypdf") from e

    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    text = "\n\n".join(parts).strip()
    if not text:
        raise Exception("PDF has no extractable text")
    return text


# --- Save helpers for AI generate ---
def _save_game_only(topic_id, game):
    GameQuestion.delete_by_topic(topic_id)
    for set_no in [1, 2, 3]:
        for tile_no, it in enumerate((game.get(str(set_no)) or [])[:24], 1):
            q, a = (it.get("question") or "").strip(), (it.get("answer") or "").strip()
            if q and a:
                GameQuestion.create(topic_id, set_no, tile_no, q, a, int(it.get("points") or 10))


def _save_practice_only(topic_id, practice):
    PracticeQuestion.delete_by_topic(topic_id)
    for it in practice or []:
        prompt = (it.get("question") or "").strip()
        choices = it.get("choices") or []
        if not prompt or len(choices) != 4:
            continue
        ci = max(0, min(int(it.get("correct_index") or 0), 3))
        PracticeQuestion.create(
            topic_id,
            "multiple_choice",
            json.dumps({"prompt": prompt, "choices": choices}),
            str(choices[ci]).strip(),
        )


def _save_slides_only(topic_id, slides):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return
    slides_json = json.dumps({"slides": slides or []}, ensure_ascii=False)
    Topic.update(topic_id, topic["name"], topic.get("description") or "", slides_json, topic.get("pdf_file"))


def _save_game_and_practice(topic_id, game, practice):
    _save_game_only(topic_id, game)
    _save_practice_only(topic_id, practice)


def _save_all(topic_id, slides, game, practice):
    _save_slides_only(topic_id, slides)
    _save_game_only(topic_id, game)
    _save_practice_only(topic_id, practice)


@app.route("/api/topic/<int:topic_id>/generate", methods=["POST"])
@login_required
@rate_limit("5/minute")
def api_generate_from_pdf(topic_id):
    is_premium = is_premium_user(session["user_id"])
    can_ai, ai_msg = UsageLimits.can_ai_generate(session["user_id"], is_premium)

    if not can_ai:
        return jsonify({"ok": False, "error": ai_msg, "upgrade_required": True}), 403

    topic = _get_topic_or_404(topic_id)
    if not topic.get("pdf_file"):
        return _json_error("No PDF", 400)

    mode = ((request.get_json(silent=True) or {}).get("mode") or "all").lower()
    path = os.path.join(app.config["UPLOAD_FOLDER"], topic["pdf_file"])
    if not os.path.exists(path):
        return _json_error("PDF not found", 404)

    try:
        text = _extract_text_from_pdf(path)
    except Exception as e:
        return _json_error(str(e), 400)

    user_id = session["user_id"]
    topic_name = topic["name"]

    _cleanup_old_tasks()
    task_id = _create_task()

    def run_pdf_generate():
        try:
            _update_task(task_id, status="generating")
            bundle = generate_lesson_bundle(
                f"{topic_name}\n\n[PDF]\n{text[:8000]}",
                "Secondary", "EN", "Minimal", "gpt-4o-mini",
            )
            with app.app_context():
                if mode == "slides":
                    _save_slides_only(topic_id, bundle.get("slides") or [])
                elif mode == "game":
                    _save_game_only(topic_id, bundle.get("game") or {})
                elif mode == "practice":
                    _save_practice_only(topic_id, bundle.get("practice") or [])
                else:
                    _save_all(topic_id, bundle.get("slides") or [],
                              bundle.get("game") or {}, bundle.get("practice") or [])
                UsageLimits.increment_ai_generate(user_id)

            _update_task(task_id, status="done", result={"ok": True})
        except Exception as e:
            _update_task(task_id, status="error", error=str(e))

    threading.Thread(target=run_pdf_generate, daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id})


# ==============================================================================
# Try Slides (No Login Required — Public Demo)
# ==============================================================================
@app.route("/try-slides")
def try_slides():
    return render_template("try_slides.html")


@app.route("/api/try-slides", methods=["POST"])
@rate_limit("3/hour")
def api_try_slides():
    """Public AI generation — limited, no login required."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Topic title required."}), 400
    if len(title) > 100:
        return jsonify({"ok": False, "error": "Title too long (max 100 chars)."}), 400

    language = data.get("language", "EN")
    if language not in ("EN", "TH", "EN+TH"):
        language = "EN"

    _cleanup_old_tasks()
    task_id = _create_task()

    def run_trial_generate():
        try:
            _update_task(task_id, status="generating")
            bundle = generate_lesson_bundle(
                title=title, level="Secondary", language=language,
                style="Minimal", text_model="gpt-4o-mini",
            )
            slides = bundle.get("slides", []) or []
            _update_task(task_id, status="done", result={
                "slides": slides[:8],
                "total_slides": len(slides),
                "title": title,
                "language": language,
                "full_bundle": {
                    "slides": slides,
                    "game": bundle.get("game") or {},
                    "practice": bundle.get("practice") or [],
                },
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            _update_task(task_id, status="error", error=str(e))

    threading.Thread(target=run_trial_generate, daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id})


@app.route("/api/try-task/<task_id>/status")
def api_try_task_status(task_id):
    """Poll endpoint for trial tasks — no login required."""
    task = _get_task(task_id)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({
        "ok": True,
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
    })


@app.route("/try-slides/save", methods=["POST"])
@login_required
def try_slides_save():
    """Save trial slides to user's account."""
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "")

    task = _get_task(task_id)
    if not task or task.get("status") != "done":
        return jsonify({"ok": False, "error": "Task not found or not complete"}), 404

    result = task.get("result", {})
    full_bundle = result.get("full_bundle", {})
    title = result.get("title", "AI Generated")
    slides = full_bundle.get("slides", [])

    if not slides:
        return jsonify({"ok": False, "error": "No slides to save"}), 400

    user_id = session["user_id"]
    is_premium = is_premium_user(user_id)
    can_create, msg = UsageLimits.can_create_topic(user_id, is_premium)
    if not can_create:
        return jsonify({"ok": False, "error": msg, "upgrade_required": True}), 403

    topic = Topic.create(
        user_id, title, "AI generated (trial)",
        json.dumps({"slides": slides}, ensure_ascii=False),
        "ai", None,
    )
    _save_game_and_practice(
        topic["id"],
        full_bundle.get("game") or {},
        full_bundle.get("practice") or [],
    )
    UsageLimits.increment_ai_generate(user_id)

    return jsonify({"ok": True, "redirect": f"/topic/{topic['id']}"})


@app.route("/try-slides/resume")
@login_required
def try_slides_resume():
    """After login, this page auto-saves trial slides using sessionStorage task_id."""
    return render_template("try_slides_resume.html")


# ==============================================================================
# Error Handlers
# ==============================================================================
@app.errorhandler(403)
def forbidden(e):
    if _wants_json_response():
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    return render_template("error.html", error_code=403, error_msg="\u0e44\u0e21\u0e48\u0e21\u0e35\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e4c"), 403


@app.errorhandler(404)
def not_found(e):
    if _wants_json_response():
        return jsonify({"ok": False, "error": "Not found"}), 404
    return render_template("error.html", error_code=404, error_msg="\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e2b\u0e19\u0e49\u0e32\u0e19\u0e35\u0e49"), 404


@app.errorhandler(500)
def server_error(e):
    if _wants_json_response():
        return jsonify({"ok": False, "error": "Server error"}), 500
    return render_template("error.html", error_code=500, error_msg="\u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14"), 500


@app.errorhandler(429)
def rate_limit_exceeded(e):
    if _wants_json_response():
        return jsonify({"ok": False, "error": "\u0e04\u0e33\u0e02\u0e2d\u0e21\u0e32\u0e01\u0e40\u0e01\u0e34\u0e19\u0e44\u0e1b \u0e01\u0e23\u0e38\u0e13\u0e32\u0e23\u0e2d\u0e2a\u0e31\u0e01\u0e04\u0e23\u0e39\u0e48"}), 429
    return render_template("error.html", error_code=429, error_msg="\u0e04\u0e33\u0e02\u0e2d\u0e21\u0e32\u0e01\u0e40\u0e01\u0e34\u0e19\u0e44\u0e1b \u0e01\u0e23\u0e38\u0e13\u0e32\u0e23\u0e2d\u0e2a\u0e31\u0e01\u0e04\u0e23\u0e39\u0e48"), 429


# ==============================================================================
# Run
# ==============================================================================
if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_ENV") == "development",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )
